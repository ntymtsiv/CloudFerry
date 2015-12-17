# Copyright 2015 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time

import test_exceptions

TIMEOUT_FOR_SERVICES_UP = 180


class CheckOpenstackServices(object):

    def __init__(self, cloud):
        self.cloud = cloud
        self.vm_ip = self.cloud.get_vagrant_vm_ip()
        self.hostname = self.cloud.migration_utils.execute_command_on_vm(
            self.cloud.get_vagrant_vm_ip(), 'hostname', username='root')

    def restart_nova_services(self, services):
        for service in services:
            print('Nova service %s is down, restarting...' % service)
            self.restart_service(service)

    def restart_neutron_agents(self, agents):
        for agent in agents:
            print('Neutron agent %s is down, restarting...' % agent)
            if agent == 'neutron-openvswitch-agent':
                agent = 'neutron-plugin-openvswitch-agent'
            self.restart_service(agent)

    def restart_service(self, service):
        cmd = 'service %s restart' % service
        self.cloud.migration_utils.execute_command_on_vm(
            self.vm_ip, cmd, username='root')

    def check_nova_services(self):
        down_services = []
        services = self.cloud.novaclient.services.list(host=self.hostname)
        for service in services:
            if service.state == 'down':
                down_services.append(service.binary)
        return down_services

    def check_neutron_agents(self):
        not_alive_agents = []
        agents = self.cloud.neutronclient.list_agents(
            host=self.hostname)['agents']
        for agent in agents:
            if not agent['alive']:
                not_alive_agents.append(agent['binary'])
        return not_alive_agents

    def wait_until_services_up(self):
        check_nova_services = True
        check_neutron = True
        down_services = []
        not_alive_agents = []
        for _ in range(TIMEOUT_FOR_SERVICES_UP):
            if check_nova_services:
                down_services = self.check_nova_services()
                check_nova_services = True if down_services else False
            if check_neutron:
                not_alive_agents = self.check_neutron_agents()
                check_neutron = True if not_alive_agents else False
            if check_nova_services is False and check_neutron is False:
                break
            else:
                time.sleep(1)
        else:
            return {'down_nova_services': down_services,
                    'not_alive_neutron_agents': not_alive_agents}

    def start(self):
        services = self.wait_until_services_up()
        if services:
            self.restart_nova_services(services['down_nova_services'])
            self.restart_neutron_agents(services['not_alive_neutron_agents'])
        services = self.wait_until_services_up()
        if services:
            msg = 'Next services in down state after attempt restart them : %s' \
                  ' Please make sure all services up and start generate load ' \
                  'again.' % [service for service in services.values()]
            raise test_exceptions.AbortGenerateLoadError(msg)
