# Copyright (c) 2015 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.

import base
import collections
import os
import yaml
import config
import time
import test_exceptions

from fabric.api import run, settings, sudo, hide, local
from fabric.network import NetworkError
from neutronclient.common.exceptions import NeutronClientException


VM_ACCESSIBILITY_ATTEMPTS = 20


def convert(data):
    """ Method converts all unicode objects to string objects"""
    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(convert, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(convert, data))
    else:
        return data


class Utils(object):
    def __init__(self):
        self.main_folder = os.path.dirname(os.path.dirname(
            os.path.split(__file__)[0]))

    def load_file(self, file_name):
        file_path = os.path.join(self.main_folder, file_name.lstrip('/'))
        with open(file_path, "r") as f:
            filter_dict = yaml.load(f)
            if filter_dict is None:
                filter_dict = {}
        return [filter_dict, file_path]


class FilteringUtils(Utils):
    def __init__(self, path_to_filter):
        super(FilteringUtils, self).__init__()
        self.filter_file_path = path_to_filter
        self.filters_file_naming_template = config.filters_file_naming_template

    def build_filter_files_list(self):
        return [self.filters_file_naming_template.format(
            tenant_name=tenant['name'])
            for tenant in config.tenants
            if 'deleted' not in tenant and not tenant['deleted']]

    def filter_vms(self, src_data_list):
        loaded_data = self.load_file(self.filter_file_path)
        filter_dict = loaded_data[0]
        popped_vm_list = []
        if 'instances' not in filter_dict:
            return [src_data_list, []]
        for vm in src_data_list[:]:
            if vm.id not in filter_dict['instances']['id']:
                popped_vm_list.append(vm)
                index = src_data_list.index(vm)
                src_data_list.pop(index)
        return [src_data_list, popped_vm_list]

    def filter_images(self, src_data_list):
        loaded_data = self.load_file(self.filter_file_path)
        filter_dict = loaded_data[0]
        popped_img_list = []
        default_img = 'Cirros 0.3.0 x86_64'
        if 'images' not in filter_dict:
            return [src_data_list, []]
        for img in src_data_list[:]:
            if img.id not in filter_dict['images']['images_list']:
                if img.name != default_img:
                    popped_img_list.append(img)
                    index = src_data_list.index(img)
                    src_data_list.pop(index)
        return [src_data_list, popped_img_list]

    def filter_volumes(self, src_data_list):
        loaded_data = self.load_file('configs/filter.yaml')
        filter_dict = loaded_data[0]
        popped_vol_list = []
        if 'volumes' not in filter_dict:
            return [src_data_list, []]
        for vol in src_data_list[:]:
            if vol.id not in filter_dict['volumes']['volumes_list']:
                popped_vol_list.append(vol)
                index = src_data_list.index(vol)
                src_data_list.pop(index)
        return [src_data_list, popped_vol_list]

    def filter_tenants(self, src_data_list):
        loaded_data = self.load_file(self.filter_file_path)
        filter_dict = loaded_data[0]
        popped_tenant_list = []
        if 'tenants' not in filter_dict:
            return [src_data_list, []]
        for tenant in src_data_list:
            if tenant.id not in filter_dict['tenants']['tenant_id']:
                popped_tenant_list.append(tenant)
                index = src_data_list.index(tenant)
                src_data_list.pop(index)
        return [src_data_list, popped_tenant_list]


class MigrationUtils(object):

    def __init__(self, conf):
        self.config = conf
        self.start_ssh_agent()

    def start_ssh_agent(self):
        if self.config.local_rsa_key_path:
            rsa_key_path = self.config.loca_rsa_key
        else:
            # check default path ~/.ssh/id_rsa and ~/.ssh/id_dsa
            for key in ('.ssh/id_rsa', '.ssh/id_dsa'):
                path_to_default_key = os.path.join(os.environ['HOME'], key)
                if os.path.exists(path_to_default_key):
                    rsa_key_path = path_to_default_key
                    break
            else:
                msg = ('RSA key was not found. Please set path to rsa key in '
                       'the config.py in variable "local_rsa_key_path"')
                raise test_exceptions.AbortGenerateLoadError(msg)

        with hide('everything'), settings(warn_only=True):
            result = local('ssh-add -l', capture=True)
            if result.succeeded:
                if rsa_key_path not in result:
                    local('ssh-add %s' % rsa_key_path)
                return
            cmd = 'eval `ssh-agent` && echo $SSH_AUTH_SOCK && ssh-add %s'
            info_agent = local(cmd % rsa_key_path, capture=True).splitlines()
            os.environ["SSH_AUTH_SOCK"] = info_agent[1]

    def execute_command_on_vm(self, ip_addr, cmd, username=None,
                              warn_only=False, password=None, key=None,
                              use_sudo=True):

        if username is None:
            username = self.config.username_for_ssh
        if password is None and key is None:
            password = self.config.password_for_ssh
        no_agent = False if ip_addr in base.OPENSTACK_RELEASES else True
        with hide('everything'), settings(
                host_string=ip_addr, user=username, password=password, key=key,
                abort_on_prompts=False, connection_attempts=3,
                disable_known_hosts=True, no_agent=no_agent,
                warn_only=warn_only):
            try:
                if use_sudo:
                    return sudo(cmd, shell=False)
                else:
                    return run(cmd, shell=False)
            except NetworkError:
                raise RuntimeError('VM with name ip: %s is not accessible'
                                   % ip_addr)

    def get_all_vms_from_config(self):
        vms = self.config.vms
        for tenant in self.config.tenants:
            if not tenant.get('vms') or tenant.get('deleted'):
                continue
            for vm in tenant['vms']:
                vms.append(vm)
        vms.extend(self.config.vms_from_volumes)
        return vms

    def get_all_images_from_config(self):
        images = self.config.images
        for tenant in self.config.tenants:
            if not tenant.get('images'):
                continue
            for image in tenant['images']:
                images.append(image)
        return images

    def wait_until_vm_accessible_via_ssh(self, ip_addr):
        for _ in range(VM_ACCESSIBILITY_ATTEMPTS):
            try:
                self.execute_command_on_vm(ip_addr, 'pwd')
                break
            except RuntimeError:
                time.sleep(1)
        else:
            msg = 'VM with ip "{}" is not accessible via ssh after {} attempts'
            raise RuntimeError(msg.format(ip_addr, VM_ACCESSIBILITY_ATTEMPTS))

    @staticmethod
    def open_ssh_port_secgroup(client, tenant_id):
        sec_grps = client.get_sec_group_id_by_tenant_id(tenant_id)
        for sec_gr in sec_grps:
            try:
                client.create_security_group_rule(
                    sec_gr, tenant_id, protocol='tcp', port_range_max=22,
                    port_range_min=22, direction='ingress')
            except NeutronClientException as e:
                if e.status_code != 409:
                    raise e

    @staticmethod
    def get_vm_fip(vm):
        for net in vm.addresses:
            for addr in vm.addresses[net]:
                if addr['OS-EXT-IPS:type'] == 'floating':
                    return addr['addr']
        raise RuntimeError('VM with name {} and id {} doesnt have fip'.format(
            vm.name, vm.id))


class AddAdminUserRoleToNonAdminTenant(object):

    def __init__(self, ks_client, admin_user, tenant):
        self.keystone = ks_client
        self.tenant = self.keystone.tenants.find(name=tenant)
        self.user = self.keystone.users.find(name=admin_user)
        self.role = self.keystone.roles.find(name='admin')
        self.user_has_role = False
        roles = self.keystone.users.list_roles(self.user.id, self.tenant.id)
        for role in roles:
            if role.id == self.role.id:
                self.user_has_role = True

    def __enter__(self):
        if not self.user_has_role:
            self.keystone.roles.add_user_role(user=self.user,
                                              role=self.role,
                                              tenant=self.tenant)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.user_has_role:
            self.keystone.roles.remove_user_role(user=self.user,
                                                 role=self.role,
                                                 tenant=self.tenant)
