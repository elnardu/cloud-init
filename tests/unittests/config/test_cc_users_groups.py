# This file is part of cloud-init. See LICENSE file for license information.
import re

import pytest

from cloudinit.config import cc_users_groups
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, mock, skipUnlessJsonSchema

MODPATH = "cloudinit.config.cc_users_groups"


@mock.patch("cloudinit.distros.ubuntu.Distro.create_group")
@mock.patch("cloudinit.distros.ubuntu.Distro.create_user")
class TestHandleUsersGroups(CiTestCase):
    """Test cc_users_groups handling of config."""

    with_logs = True

    def test_handle_no_cfg_creates_no_users_or_groups(self, m_user, m_group):
        """Test handle with no config will not create users or groups."""
        cfg = {}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        m_user.assert_not_called()
        m_group.assert_not_called()

    def test_handle_users_in_cfg_calls_create_users(self, m_user, m_group):
        """When users in config, create users with distro.create_user."""
        cfg = {"users": ["default", {"name": "me2"}]}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call("me2", default=False),
            ],
        )
        m_group.assert_not_called()

    @mock.patch("cloudinit.distros.freebsd.Distro.create_group")
    @mock.patch("cloudinit.distros.freebsd.Distro.create_user")
    def test_handle_users_in_cfg_calls_create_users_on_bsd(
        self,
        m_fbsd_user,
        m_fbsd_group,
        m_linux_user,
        m_linux_group,
    ):
        """When users in config, create users with freebsd.create_user."""
        cfg = {"users": ["default", {"name": "me2"}]}  # merged cloud-config
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "freebsd",
                "lock_passwd": True,
                "groups": ["wheel"],
                "shell": "/bin/tcsh",
            }
        }
        metadata = {}
        cloud = self.tmp_cloud(
            distro="freebsd", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        self.assertCountEqual(
            m_fbsd_user.call_args_list,
            [
                mock.call(
                    "freebsd",
                    groups="wheel",
                    lock_passwd=True,
                    shell="/bin/tcsh",
                ),
                mock.call("me2", default=False),
            ],
        )
        m_fbsd_group.assert_not_called()
        m_linux_group.assert_not_called()
        m_linux_user.assert_not_called()

    def test_users_with_ssh_redirect_user_passes_keys(self, m_user, m_group):
        """When ssh_redirect_user is True pass default user and cloud keys."""
        cfg = {
            "users": ["default", {"name": "me2", "ssh_redirect_user": True}]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call(
                    "me2",
                    cloud_public_ssh_keys=["key1"],
                    default=False,
                    ssh_redirect_user="ubuntu",
                ),
            ],
        )
        m_group.assert_not_called()

    def test_users_with_ssh_redirect_user_default_str(self, m_user, m_group):
        """When ssh_redirect_user is 'default' pass default username."""
        cfg = {
            "users": [
                "default",
                {"name": "me2", "ssh_redirect_user": "default"},
            ]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call(
                    "me2",
                    cloud_public_ssh_keys=["key1"],
                    default=False,
                    ssh_redirect_user="ubuntu",
                ),
            ],
        )
        m_group.assert_not_called()

    def test_users_without_home_cannot_import_ssh_keys(self, m_user, m_group):
        cfg = {
            "users": [
                "default",
                {
                    "name": "me2",
                    "ssh_import_id": ["snowflake"],
                    "no_create_home": True,
                },
            ]
        }
        cloud = self.tmp_cloud(distro="ubuntu", sys_cfg={}, metadata={})
        with self.assertRaises(ValueError) as context_manager:
            cc_users_groups.handle("modulename", cfg, cloud, None, None)
        m_group.assert_not_called()
        self.assertEqual(
            "Not creating user me2. Key(s) ssh_import_id cannot be provided"
            " with no_create_home",
            str(context_manager.exception),
        )

    def test_users_with_ssh_redirect_user_non_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is not 'default'."""
        cfg = {
            "users": [
                "default",
                {"name": "me2", "ssh_redirect_user": "snowflake"},
            ]
        }
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        with self.assertRaises(ValueError) as context_manager:
            cc_users_groups.handle("modulename", cfg, cloud, None, None)
        m_group.assert_not_called()
        self.assertEqual(
            "Not creating user me2. Invalid value of ssh_redirect_user:"
            " snowflake. Expected values: true, default or false.",
            str(context_manager.exception),
        )

    def test_users_with_ssh_redirect_user_default_false(self, m_user, m_group):
        """When unspecified ssh_redirect_user is false and not set up."""
        cfg = {"users": ["default", {"name": "me2"}]}
        # System config defines a default user for the distro.
        sys_cfg = {
            "default_user": {
                "name": "ubuntu",
                "lock_passwd": True,
                "groups": ["lxd", "sudo"],
                "shell": "/bin/bash",
            }
        }
        metadata = {"public-keys": ["key1"]}
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        self.assertCountEqual(
            m_user.call_args_list,
            [
                mock.call(
                    "ubuntu",
                    groups="lxd,sudo",
                    lock_passwd=True,
                    shell="/bin/bash",
                ),
                mock.call("me2", default=False),
            ],
        )
        m_group.assert_not_called()

    def test_users_ssh_redirect_user_and_no_default(self, m_user, m_group):
        """Warn when ssh_redirect_user is True and no default user present."""
        cfg = {
            "users": ["default", {"name": "me2", "ssh_redirect_user": True}]
        }
        # System config defines *no* default user for the distro.
        sys_cfg = {}
        metadata = {}  # no public-keys defined
        cloud = self.tmp_cloud(
            distro="ubuntu", sys_cfg=sys_cfg, metadata=metadata
        )
        cc_users_groups.handle("modulename", cfg, cloud, None, None)
        m_user.assert_called_once_with("me2", default=False)
        m_group.assert_not_called()
        self.assertEqual(
            "WARNING: Ignoring ssh_redirect_user: True for me2. No"
            " default_user defined. Perhaps missing"
            " cloud configuration users:  [default, ..].\n",
            self.logs.getvalue(),
        )


class TestUsersGroupsSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Validate default settings not covered by examples
            ({"groups": ["anygrp"]}, None),
            ({"groups": "anygrp,anyothergroup"}, None),  # DEPRECATED
            # Create anygrp with user1 as member
            ({"groups": [{"anygrp": "user1"}]}, None),
            # Create anygrp with user1 as member using object/string syntax
            ({"groups": {"anygrp": "user1"}}, None),
            # Create anygrp with user1 as member using object/list syntax
            ({"groups": {"anygrp": ["user1"]}}, None),
            ({"groups": [{"anygrp": ["user1", "user2"]}]}, None),
            # Make default username "olddefault": DEPRECATED
            ({"user": "olddefault"}, None),
            # Create multiple users, and include default user. DEPRECATED
            ({"users": "oldstyle,default"}, None),
            ({"users": ["default"]}, None),
            ({"users": ["default", ["aaa", "bbb"]]}, None),
            ({"users": ["foobar"]}, None),  # no default user creation
            ({"users": [{"name": "bbsw"}]}, None),
            ({"groups": [{"yep": ["user1"]}]}, None),
            (
                {"user": ["no_list_allowed"]},
                re.escape("user: ['no_list_allowed'] is not valid "),
            ),
            (
                {"groups": {"anygrp": 1}},
                "groups.anygrp: 1 is not of type 'string', 'array'",
            ),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
