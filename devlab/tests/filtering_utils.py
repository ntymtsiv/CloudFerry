import os
import yaml
import config


class FilteringUtils:
    def __init__(self):
        # TODO:
        #  Using relative paths is a bad practice, unfortunately this is the
        #  only way at this moment.
        #  Should be fixed by implementing proper package module for
        #  Cloud Ferry.
        self.main_folder = os.path.dirname(os.path.dirname(os.getcwd()))

    def load_file(self):
        file_name = 'configs/filter.yaml'
        file_path = os.path.join(self.main_folder, file_name)
        filtering = open(file_path, 'r')
        filter_dict = yaml.load(filtering)
        return [filter_dict, file_path]

    def filter_vms(self, src_data_list):
        loaded_data = self.load_file()
        filter_dict = loaded_data[0]
        popped_vm_list = []
        for vm in src_data_list[:]:
            if vm['id'] not in filter_dict['instances']['id']:
                popped_vm_list.append(vm)
                index = src_data_list.index(vm)
                src_data_list.pop(index)
        return [src_data_list, popped_vm_list]

    def filter_images(self, src_data_list):
        loaded_data = self.load_file()
        filter_dict = loaded_data[0]
        popped_img_list = []
        default_img = 'Cirros 0.3.0 x86_64'
        src_data_list = [x.__dict__ for x in src_data_list]
        for img in src_data_list[:]:
            if img['id'] not in filter_dict['images']['images_list']:
                if img['name'] != default_img:
                    popped_img_list.append(img)
                    index = src_data_list.index(img)
                    src_data_list.pop(index)
        return [src_data_list, popped_img_list]

    def get_resource_names(self, obj, cfg):
        if obj == 'routers':
            return [i['router']['name'] for i in cfg]
        else:
            return [i['name'] for i in cfg]

    def get_resources_from_config(self, res):
        if res == 'security_groups':
            return [sg for i in config.tenants if 'security_groups' in i
                    for sg in i['security_groups']]
        elif res == 'servers':
            cfg = getattr(config, 'vms')
            [cfg.extend(i['vms']) for i in config.tenants if 'vms' in i]
            return cfg
        elif res == 'volumes':
            res = 'cinder_volumes'

        return getattr(config, res)
