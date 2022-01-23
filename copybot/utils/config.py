import yaml
import os

class Configuration:
    def __init__(self, path_to_config):
        path = os.path.abspath(path_to_config)
        
        with open(path_to_config, 'r') as file:
            try:
                self.config = yaml.safe_load(file)
            except yaml.YAMLError as excep:
                raise(excep)
    
    def get_config(self) -> dict:
        return self.config
