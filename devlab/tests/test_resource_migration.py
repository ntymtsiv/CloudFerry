import config
import exception
import functional_test
import itertools

import pprint
import unittest

from fabric.api import run, settings
from fabric.network import NetworkError


class ResourceMigrationTests(functional_test.FunctionalTest):

    def validate_resource_parameter_in_dst(self, src_list, dst_list,
                                           resource_name, parameter):
        if not src_list:
            self.skipTest(
                'Nothing to migrate - source resources list is empty')
        name_attr = 'name'
        if resource_name == 'volume':
            name_attr = 'display_name'
        for i in src_list:
            for j in dst_list:
                if getattr(i, name_attr) != getattr(j, name_attr):
                    continue
                if getattr(i, parameter) != getattr(j, parameter):
                    msg = 'Parameter {param} for resource {res} with name ' \
                          '{name} are different src: {r1}, dst: {r2}'
                    self.fail(msg.format(
                        param=parameter, res=resource_name,
                        name=getattr(i, name_attr), r1=getattr(i, parameter),
                        r2=getattr(j, parameter)))
                break
            else:
                msg = 'Resource {res} with name {r_name} was not found on dst'
                self.fail(msg.format(res=resource_name,
                                     r_name=getattr(i, name_attr)))

    def validate_neutron_resource_parameter_in_dst(self, src_list, dst_list,
                                                   resource_name='networks',
                                                   parameter='name'):
        if not src_list[resource_name]:
            self.skipTest(
                'Nothing to migrate - source resources list is empty')
        for i in src_list[resource_name]:
            for j in dst_list[resource_name]:
                if i['name'] != j['name']:
                    continue
                if i[parameter] != j[parameter]:
                    msg = 'Parameter {param} for resource {res} with name ' \
                          '{name} are different src: {r1}, dst: {r2}'
                    self.fail(msg.format(
                        param=parameter, res=resource_name, name=i['name'],
                        r1=i[parameter], r2=j[parameter]))
                break
            else:
                msg = 'Resource {res} with name {r_name} was not found on dst'
                self.fail(msg.format(res=resource_name, r_name=i['name']))

    def test_migrate_keystone_users(self):
        src_users = self.filter_users()
        dst_users = self.dst_cloud.keystoneclient.users.list()

        self.validate_resource_parameter_in_dst(src_users, dst_users,
                                                resource_name='user',
                                                parameter='name')
        self.validate_resource_parameter_in_dst(src_users, dst_users,
                                                resource_name='user',
                                                parameter='email')

    def test_migrate_keystone_user_tenant_roles(self):
        src_users = self.filter_users()
        src_user_names = [user.name for user in src_users]
        dst_users = self.dst_cloud.keystoneclient.users.list()
        least_user_match = False
        for dst_user in dst_users:
            if dst_user.name not in src_user_names:
                continue
            least_user_match = True
            src_user_tnt_roles = self.src_cloud.get_user_tenant_roles(dst_user)
            dst_user_tnt_roles = self.dst_cloud.get_user_tenant_roles(dst_user)
            self.validate_resource_parameter_in_dst(
                src_user_tnt_roles, dst_user_tnt_roles,
                resource_name='user_tenant_role', parameter='name')
        msg = ("Either migration is not initiated or it was not successful for"
               " resource 'USER'.")
        self.assertTrue(least_user_match, msg=msg)

    def test_migrate_keystone_roles(self):
        src_roles = self.filter_roles()
        dst_roles = self.dst_cloud.keystoneclient.roles.list()

        self.validate_resource_parameter_in_dst(src_roles, dst_roles,
                                                resource_name='role',
                                                parameter='name')

    def test_migrate_keystone_tenants(self):
        src_tenants = self.filter_tenants()
        dst_tenants_gen = self.dst_cloud.keystoneclient.tenants.list()
        dst_tenants = [x for x in dst_tenants_gen]

        filtering_data = self.filtering_utils.filter_tenants(src_tenants)
        src_tenants = filtering_data[0]

        self.validate_resource_parameter_in_dst(src_tenants, dst_tenants,
                                                resource_name='tenant',
                                                parameter='name')
        self.validate_resource_parameter_in_dst(src_tenants, dst_tenants,
                                                resource_name='tenant',
                                                parameter='description')

    def test_migrate_nova_keypairs(self):
        src_keypairs = self.filter_keypairs()
        dst_keypairs = self.dst_cloud.get_users_keypairs()

        self.validate_resource_parameter_in_dst(src_keypairs, dst_keypairs,
                                                resource_name='keypair',
                                                parameter='name')
        self.validate_resource_parameter_in_dst(src_keypairs, dst_keypairs,
                                                resource_name='keypair',
                                                parameter='fingerprint')

    def test_migrate_nova_flavors(self):
        src_flavors = self.filter_flavors()
        dst_flavors = self.dst_cloud.novaclient.flavors.list()

        self.validate_resource_parameter_in_dst(src_flavors, dst_flavors,
                                                resource_name='flavor',
                                                parameter='name')
        self.validate_resource_parameter_in_dst(src_flavors, dst_flavors,
                                                resource_name='flavor',
                                                parameter='ram')
        self.validate_resource_parameter_in_dst(src_flavors, dst_flavors,
                                                resource_name='flavor',
                                                parameter='vcpus')
        self.validate_resource_parameter_in_dst(src_flavors, dst_flavors,
                                                resource_name='flavor',
                                                parameter='disk')
        # Id can be changed, but for now in CloudFerry we moving flavor with
        # its id.
        self.validate_resource_parameter_in_dst(src_flavors, dst_flavors,
                                                resource_name='flavor',
                                                parameter='id')

    def test_migrate_nova_security_groups(self):
        src_sec_gr = self.filter_security_groups()
        dst_sec_gr = self.dst_cloud.neutronclient.list_security_groups()
        self.validate_neutron_resource_parameter_in_dst(
            src_sec_gr, dst_sec_gr, resource_name='security_groups',
            parameter='name')
        self.validate_neutron_resource_parameter_in_dst(
            src_sec_gr, dst_sec_gr, resource_name='security_groups',
            parameter='description')

    def test_image_members(self):

        def member_list_collector(_images, client, auth_client):
            _members = []
            for img in _images:
                members = client.image_members.list(img.id)
                if not members:
                    continue
                mbr_list = []
                for mem in members:
                    mem_name = auth_client.tenants.find(id=mem.member_id).name
                    mbr_list.append(mem_name)
                _members.append({img.name: sorted(mbr_list)})
            return sorted(_members)

        src_images = self.filter_images()
        dst_images = [x for x in self.dst_cloud.glanceclient.images.list()]
        src_images = self.filtering_utils.filter_images(src_images)[0]

        src_members = member_list_collector(src_images,
                                            self.src_cloud.glanceclient,
                                            self.src_cloud.keystoneclient)
        dst_members = member_list_collector(dst_images,
                                            self.dst_cloud.glanceclient,
                                            self.dst_cloud.keystoneclient)
        self.assertListEqual(src_members, dst_members)

    def test_migrate_glance_images(self):
        src_images = self.filter_images()
        dst_images_gen = self.dst_cloud.glanceclient.images.list()
        dst_images = [x for x in dst_images_gen]

        filtering_data = self.filtering_utils.filter_images(src_images)
        src_images = filtering_data[0]

        self.validate_resource_parameter_in_dst(src_images, dst_images,
                                                resource_name='image',
                                                parameter='name')
        self.validate_resource_parameter_in_dst(src_images, dst_images,
                                                resource_name='image',
                                                parameter='disk_format')
        self.validate_resource_parameter_in_dst(src_images, dst_images,
                                                resource_name='image',
                                                parameter='container_format')
        self.validate_resource_parameter_in_dst(src_images, dst_images,
                                                resource_name='image',
                                                parameter='size')
        self.validate_resource_parameter_in_dst(src_images, dst_images,
                                                resource_name='image',
                                                parameter='checksum')

    def test_migrate_glance_belongs_to_deleted_tenant(self):
        src_images = self.filter_images()
        src_tnt_ids = [i.id for i in self.filter_tenants()]
        src_tnt_ids.append(self.src_cloud.get_tenant_id(self.src_cloud.tenant))
        src_images = [i.name for i in src_images if i.owner not in src_tnt_ids]

        dst_images = self.dst_cloud.glanceclient.images.list()
        dst_tenant_id = self.dst_cloud.get_tenant_id(self.dst_cloud.tenant)

        least_image_check = False
        for image in dst_images:
            if image.name not in src_images:
                continue
            least_image_check = True
            self.assertEqual(image.owner, dst_tenant_id,
                             'Image owner on dst is {0} instead of {1}'.format(
                                 image.owner, dst_tenant_id))
        msg = ("Either migration is not initiated or it was not successful for"
               " resource 'Image'.")
        self.assertTrue(least_image_check, msg=msg)

    def test_glance_images_not_in_filter_did_not_migrate(self):
        src_images = self.filter_images()
        filtering_data = self.filtering_utils.filter_images(src_images)
        dst_images_gen = self.dst_cloud.glanceclient.images.list()
        dst_images = [x.name for x in dst_images_gen]
        images_filtered_out = filtering_data[1]
        for image in images_filtered_out:
            self.assertTrue(image.name not in dst_images,
                            'Image migrated despite that it was not included '
                            'in filter, Image info: \n{}'.format(image))

    def test_migrate_neutron_networks(self):
        src_nets = self.filter_networks()
        dst_nets = self.dst_cloud.neutronclient.list_networks()

        self.validate_neutron_resource_parameter_in_dst(src_nets, dst_nets)
        self.validate_neutron_resource_parameter_in_dst(
            src_nets, dst_nets, parameter='provider:network_type')
        self.validate_neutron_resource_parameter_in_dst(
            src_nets, dst_nets, parameter='provider:segmentation_id')

    def test_migrate_neutron_subnets(self):
        src_subnets = self.filter_subnets()
        dst_subnets = self.dst_cloud.neutronclient.list_subnets()

        self.validate_neutron_resource_parameter_in_dst(
            src_subnets, dst_subnets, resource_name='subnets')
        self.validate_neutron_resource_parameter_in_dst(
            src_subnets, dst_subnets, resource_name='subnets',
            parameter='gateway_ip')
        self.validate_neutron_resource_parameter_in_dst(
            src_subnets, dst_subnets, resource_name='subnets',
            parameter='cidr')

    def test_migrate_neutron_routers(self):
        src_routers = self.filter_routers()
        dst_routers = self.dst_cloud.neutronclient.list_routers()
        self.validate_neutron_resource_parameter_in_dst(
            src_routers, dst_routers, resource_name='routers')

    def test_migrate_vms_parameters(self):
        src_vms = self.filter_vms()
        dst_vms = self.dst_cloud.novaclient.servers.list(
            search_opts={'all_tenants': 1})

        filtering_data = self.filtering_utils.filter_vms(src_vms)
        src_vms = filtering_data[0]

        src_vms = [vm for vm in src_vms if vm.status != 'ERROR']

        self.validate_resource_parameter_in_dst(
            src_vms, dst_vms, resource_name='VM', parameter='name')
        self.validate_resource_parameter_in_dst(
            src_vms, dst_vms, resource_name='VM', parameter='config_drive')
        self.validate_resource_parameter_in_dst(
            src_vms, dst_vms, resource_name='VM', parameter='key_name')

    def test_migrate_vms_with_floating(self):
        vm_names_with_fip = self.get_vms_with_fip_associated()
        dst_vms = self.dst_cloud.novaclient.servers.list(
            search_opts={'all_tenants': 1})
        for vm in dst_vms:
            if vm.name not in vm_names_with_fip:
                continue
            for net in vm.addresses.values():
                if [True for addr in net if 'floating' in addr.values()]:
                    break
            else:
                raise RuntimeError('Vm {0} does not have floating ip'.format(
                    vm.name))

    def test_migrate_cinder_volumes(self):

        src_volume_list = self.filter_volumes()
        dst_volume_list = self.dst_cloud.cinderclient.volumes.list(
            search_opts={'all_tenants': 1})

        self.validate_resource_parameter_in_dst(
            src_volume_list, dst_volume_list, resource_name='volume',
            parameter='display_name')
        self.validate_resource_parameter_in_dst(
            src_volume_list, dst_volume_list, resource_name='volume',
            parameter='size')
        self.validate_resource_parameter_in_dst(
            src_volume_list, dst_volume_list, resource_name='volume',
            parameter='bootable')

    def test_migrate_cinder_volumes_data(self):
        def check_file_valid(filename):
            get_md5_cmd = 'md5sum %s' % filename
            get_old_md5_cmd = 'cat %s_md5' % filename
            md5sum = self.migration_utils.execute_command_on_vm(
                vm_ip, get_md5_cmd).split()[0]
            old_md5sum = self.migration_utils.execute_command_on_vm(
                vm_ip, get_old_md5_cmd).split()[0]
            if md5sum != old_md5sum:
                msg = "MD5 of file %s before and after migrate is different"
                raise RuntimeError(msg % filename)

        volumes = config.cinder_volumes
        volumes += itertools.chain(*[tenant['cinder_volumes'] for tenant
                                     in config.tenants if 'cinder_volumes'
                                     in tenant])
        for volume in volumes:
            attached_volume = volume.get('server_to_attach')
            if not volume.get('write_to_file') or not attached_volume:
                continue
            vm = self.dst_cloud.novaclient.servers.get(
                self.dst_cloud.get_vm_id(volume['server_to_attach']))
            vm_ip = self.migration_utils.get_vm_fip(vm)
            self.migration_utils.open_ssh_port_secgroup(self.dst_cloud,
                                                        vm.tenant_id)
            self.migration_utils.wait_until_vm_accessible_via_ssh(vm_ip)
            cmd = 'mount {0} {1}'.format(volume['device'],
                                         volume['mount_point'])
            self.migration_utils.execute_command_on_vm(vm_ip, cmd,
                                                       warn_only=True)
            for _file in volume['write_to_file']:
                check_file_valid(volume['mount_point'] + _file['filename'])

    @unittest.skip("Temporarily disabled: snapshots doesn't implemented in "
                   "cinder's nfs driver")
    def test_migrate_cinder_snapshots(self):
        src_volume_list = self.filter_volumes()
        dst_volume_list = self.dst_cloud.cinderclient.volume_snapshots.list(
            search_opts={'all_tenants': 1})

        self.validate_resource_parameter_in_dst(
            src_volume_list, dst_volume_list, resource_name='volume',
            parameter='display_name')
        self.validate_resource_parameter_in_dst(
            src_volume_list, dst_volume_list, resource_name='volume',
            parameter='size')

    def test_migrate_tenant_quotas(self):
        """
        Validate tenant's quotas were migrated to correct tenant
        """

        def get_tenant_quotas(tenants, client):
            """
            Method gets nova and neutron quotas for given tenants, and saves
            quotas, which are exist on src (on dst could exists quotas, which
            are not exist on src).
            """
            qs = {}
            for t in tenants:
                qs[t.name] = {'nova_q': {}, 'neutron_q': {}}
                nova_quota = client.novaclient.quotas.get(t.id)._info
                for k, v in nova_quota.iteritems():
                    if k in src_nova_quota_keys and k != 'id':
                        qs[t.name]['nova_q'][k] = v
                neutron_quota = client.neutronclient.show_quota(t.id)['quota']
                for k, v in neutron_quota.iteritems():
                    if k in src_neutron_quota_keys:
                        qs[t.name]['neutron_q'][k] = v
            return qs

        src_nova_quota_keys = self.src_cloud.novaclient.quotas.get(
            self.src_cloud.keystoneclient.tenant_id)._info.keys()
        src_neutron_quota_keys = self.src_cloud.neutronclient.show_quota(
            self.src_cloud.keystoneclient.tenant_id)['quota'].keys()

        src_quotas = get_tenant_quotas(self.filter_tenants(), self.src_cloud)
        dst_quotas = get_tenant_quotas(
            self.dst_cloud.keystoneclient.tenants.list(), self.dst_cloud)

        for tenant in src_quotas:
            self.assertIn(tenant, dst_quotas,
                          'Tenant %s is missing on dst' % tenant)
            # Check nova quotas
            self.assertDictEqual(
                src_quotas[tenant]['nova_q'], dst_quotas[tenant]['nova_q'],
                'Nova quotas for tenant %s migrated not successfully' % tenant)
            # Check neutron quotas
            self.assertDictEqual(
                src_quotas[tenant]['neutron_q'],
                dst_quotas[tenant]['neutron_q'],
                'Neutron quotas for tenant %s migrated not successfully'
                % tenant)

    def test_ssh_connectivity_by_keypair(self):
        vms = self.dst_cloud.novaclient.servers.list(
            search_opts={'all_tenants': 1})
        for _vm in vms:
            if 'keypair_test' in _vm.name:
                vm = _vm
                break
        else:
            raise RuntimeError(
                'VM for current test was not spawned on dst. Make sure vm with'
                'name keypair_test has been created on src')
        ip_addr = self.migration_utils.get_vm_fip(vm)
        # make sure 22 port in sec group is open
        self.migration_utils.open_ssh_port_secgroup(self.dst_cloud,
                                                    vm.tenant_id)
        # try to connect to vm via key pair
        with settings(host_string=ip_addr, user="root",
                      key=config.private_key['id_rsa'],
                      abort_on_prompts=True, connection_attempts=3,
                      disable_known_hosts=True):
            try:
                run("pwd", shell=False)
            except NetworkError:
                msg = 'VM with name {name} and ip: {addr} is not accessible'
                self.fail(msg.format(name=vm.name, addr=ip_addr))
            except SystemExit:
                msg = 'VM with name {name} and ip: {addr} is not accessible ' \
                      'via key pair'
                self.fail(msg.format(name=vm.name, addr=ip_addr))

    def test_floating_ips_migrated(self):
        def get_fips(client):
            return set([fip['floating_ip_address']
                        for fip in client.list_floatingips()['floatingips']])

        src_fips = self.filter_floatingips()
        dst_fips = get_fips(self.dst_cloud.neutronclient)

        missing_fips = src_fips - dst_fips

        if missing_fips:
            self.fail("{num} floating IPs did not migrate to destination: "
                      "{fips}".format(num=len(missing_fips),
                                      fips=pprint.pformat(missing_fips)))

    @unittest.skipUnless(functional_test.cfglib.CONF.migrate.change_router_ips,
                         'Change router ips disabled in CloudFerry config')
    def test_ext_router_ip_changed(self):
        dst_routers = self.dst_cloud.get_ext_routers()
        src_routers = self.src_cloud.get_ext_routers()
        for dst_router in dst_routers:
            for src_router in src_routers:
                if dst_router['name'] != src_router['name']:
                    continue
                src_gateway = self.src_cloud.neutronclient.list_ports(
                    device_id=src_router['id'],
                    device_owner='network:router_gateway')['ports'][0]
                dst_gateway = self.dst_cloud.neutronclient.list_ports(
                    device_id=dst_router['id'],
                    device_owner='network:router_gateway')['ports'][0]
                self.assertNotEqual(
                    src_gateway['fixed_ips'][0]['ip_address'],
                    dst_gateway['fixed_ips'][0]['ip_address'],
                    'GW ip addresses of router "{0}" are same on src and dst:'
                    ' {1}'.format(dst_router['name'],
                                  dst_gateway['fixed_ips'][0]['ip_address']))

    def test_not_valid_vms_did_not_migrate(self):
        all_vms = self.migration_utils.get_all_vms_from_config()
        vms = [vm['name'] for vm in all_vms if vm.get('broken')]
        migrated_vms = []
        for vm in vms:
            try:
                self.dst_cloud.get_vm_id(vm)
                migrated_vms.append(vm)
            except exception.NotFound:
                pass
        if migrated_vms:
            self.fail('Not valid vms %s migrated')

    def test_not_valid_images_did_not_migrate(self):
        all_images = self.migration_utils.get_all_images_from_config()
        images = [image['name'] for image in all_images if image.get('broken')]
        migrated_images = []
        for image in images:
            try:
                self.dst_cloud.get_image_id(image)
                migrated_images.append(image)
            except exception.NotFound:
                pass
        if migrated_images:
            self.fail('Not valid images %s migrated')
