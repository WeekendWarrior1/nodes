import asyncio
import tornado
import tornado.web
import tornado.ioloop
import tornado.websocket

import chevron # tornado.render() doesn't support all the moustache we require to render index.mst
import os
import sys
import random
# from typing import Optional  # noqa
import logging

import json
import yaml
import copy

from build_node import build_component_nodes

_LOGGER = logging.getLogger(__name__)

editor_client_dir = os.path.join("node_modules","@node-red","editor-client")

schemas = {}
node_schemas = {}

configs_dir = ""
websockets = []
# TODO this is just to store some user settings to return, very simple and has no persistence
user = {}
flows = []
# TODO this needs to be generated same time as nodes_html.html
nodesObj = [
    {
		"id": "node-red/junction",
		"name": "junction",
		"types": [
			"junction"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "node-red",
		"version": "3.0.0"
	},
    {
		"id": "esphome/binary_light",
		"name": "Binary Light",
		"types": [
			"binary_light"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	},
    {
		"id": "esphome/binary_sensor",
		"name": "GPIO Binary Sensor",
		"types": [
			"binary_sensor"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	},
    {
		"id": "esphome/wifi",
		"name": "wifi",
		"types": [
			"wifi"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	},
    {
		"id": "esphome/esp32",
		"name": "esp32",
		"types": [
			"esp32"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	},
    {
		"id": "esphome/gpio_output",
		"name": "gpio_output",
		"types": [
			"gpio_output"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	},
    {
		"id": "esphome/conditional",
		"name": "conditional",
		"types": [
			"conditional"
		],
		"enabled": True,
		"local": False,
		"user": False,
		"module": "esphome",
		"version": "3.0.0"
	}
    # conditional
]
node_config_types = ['gpio_output']
nodes_without_ids = ['esphome', 'esp32']
cores_without_names = ['wifi']
conditional_nodes = ['conditional']
util_nodes = ['conditional']

# generate X length char hex string (https://stackoverflow.com/a/2782859)
def buildRandomHexString(length):
    return f'%0{length}x' % random.randrange(16**length)

def doesNodeObjectExistInFlows(local_flows, key, value):
    for i in local_flows:
        if i.has(key) and i[key] == value:
            return i
    return False

def get_or_build_flows_file(flows_dir):
    # TODO can I use these within esphome lol?
    global flows
    # files_in_dir = os.listdir(os.path.join(os.path.dirname(__file__), flows_dir))
    files_in_dir = os.listdir(flows_dir)
    potential_flows = []
    for filename in files_in_dir:
        if filename.endswith('.flows'):
            # with open(os.path.join(os.path.dirname(__file__), flows_dir, filename)) as f:
            with open(os.path.join(flows_dir, filename)) as f:
                potential_flows.append(json.loads(f.read()))
    if len(potential_flows) == 0:
        potential_flows.append(build_flows_object(flows_dir))
        # TODO variable filename for flows just like esphome?
        # with open(os.path.join(os.path.dirname(__file__), flows_dir, f"esphome_node_flows.flows"), 'w') as f:
        with open(os.path.join(flows_dir, f"esphome_node_flows.flows"), 'w') as f:
            f.write(json.dumps(potential_flows[0], indent=2))
        flows = potential_flows[0]
    elif len(potential_flows) == 1:
        flows = potential_flows[0]
    else:
        # TODO find how node-red handles this
        print("multiple .flows files found")
    # TESTING BUILDING YAML HERE
    # flow_to_esphome_yaml(flows)

def build_flows_object(flows_dir):
    # TODO all directories need to be configurable, or locked into a sensible default
    configs = loadESPHomeConfigs(flows_dir)
    final_flows = {'flows':[],'rev': buildRandomHexString(32)}
    for config in configs:
        # TODO make flow-tab as a class
        flow = { 'type': 'tab'}
        flow['id'] = buildRandomHexString(16)
        flow['label'] = config['esphome']['name']
        flow['disabled'] = False
        flow['info'] = json.dumps(config, indent=2)
        flow['env'] = [] # TODO should secrets go here??
        final_flows['flows'].append(flow)
    return final_flows
    
def loadESPHomeConfigs(configs_dir):
    files_in_dir = os.listdir(os.path.join(os.path.dirname(__file__), configs_dir))
    configs = []
    for filename in files_in_dir:
        if (filename.endswith('.yaml') or filename.endswith('.yml')) and filename != 'secrets.yaml':
            # with open(os.path.join(os.path.dirname(__file__), configs_dir, filename)) as f:
            with open(os.path.join(configs_dir, filename)) as f:
                # TODO use ESPHomeLoader fromm esphome/yaml_util.py to handle all the esphome specific yaml stuff like !secret
                config = yaml.load(f, Loader=yaml.FullLoader)
                configs.append(config)
    return configs

def save_flows_to_file(flows_dir, flows_to_save):
    # with open(os.path.join(os.path.dirname(__file__), flows_dir, f"esphome_node_flows.flows"), 'w') as f:
    with open(os.path.join(flows_dir, f"esphome_node_flows.flows"), 'w') as f:
        f.write(json.dumps(flows_to_save, indent=2))

def remove_node_red_editor_props(node):
    props_to_remove = ['core','automations', 'actions']
    for prop in props_to_remove:
        if node.get(prop):
            del node[prop]
    return node

def flow_to_esphome_yaml(flows):
    '''
    this func should parse the flows and convert it into yaml
    currently should assume that I am only working in first tab
    will need to find all inputs, and run down all strings they are connected to
    '''
    flow = flows['flows']
    editor_tabs = []
    children_nodes = {}
    for node in flow:
        if (node.get('type') == 'tab'):
            editor_tabs.append(node)
    if not len(editor_tabs):
        return
    # TODO: hardcoded to only look at first flow tab
    # Use flow tab as esphome core configuration
    children_nodes[editor_tabs[0]['id']] = {
        'id': editor_tabs[0]['id'],
        'name': editor_tabs[0].get('label'),
        'esphome': {
            'core': 'esphome',
            'comment': editor_tabs[0].get('info')
        }
    }
    # TODO: hardcoded to only look at first flow tab
    for node in flow:
        if (node.get('z') == editor_tabs[0]['id'] or node.get('type') in node_config_types):
            children_nodes[node['id']] = node

    config = {}
    # for node_id in top_nodes:
    for node_id in children_nodes:
        recursive_parse_wires_and_add_to_config(config, children_nodes, children_nodes[node_id])
    final_config = {}   # esphome json has a particular structure that is painful to work with, so we use 'config' as an intermediate 
                        # (mainly we want to store components within dict with id as key instead of entries in list)
    for node_id in config:
        core = config[node_id].get('core')
        platform = config[node_id].get('platform')
        if (core in nodes_without_ids):
            del config[node_id]['id']
        if (core and platform):
        if core not in final_config:
            final_config[core] = []
        remove_node_red_editor_props(config[node_id])
        final_config[core].append(config[node_id])
        # base properties like esphome, wifi, api don't sit in arrays - (powersupply, i2c, external_components doesn't abide by this)
        elif (core and not platform):
            remove_node_red_editor_props(config[node_id])
            final_config[core] = config[node_id]

        
    print(yaml.dump(final_config))

def recursive_parse_wires_and_add_to_config(config, all_nodes, current_node):
    '''
    if not in config, add to config (using ID for now)
    for children, if automation -> action, add under parent in config
    if children, process children
    '''
    # TODO handle non esphome nodes
    if current_node['id'] not in config:
        config[current_node['id']] = copy.deepcopy(current_node['esphome'])
        config[current_node['id']]['id'] = current_node['id']
        # TODO if schema allows name
        if config[current_node['id']]['core'] not in cores_without_names and current_node.get('name'):
            config[current_node['id']]['name'] = current_node['name']
    if (current_node.get('wires')):
    for i, output in enumerate(current_node['wires']):
        if len(output):
            # found a downstream node
            for child_id in output:
                    # TODO keep track of where we are on our object
                    # for now, unattach the else, that will probably need to be recorded further down the track within the node config
                    #  what's on the other side of an action? is it a condition? or an automation? split in path based on that

                    # if child is an action, push a then to the main object
                child_node = all_nodes[child_id]
                if not current_node['esphome']['automations'][i] in config[current_node['id']]:
                    config[current_node['id']][current_node['esphome']['automations'][i]] = {'then': []}
                    # if child is an conditional, push a if, condition, then, else to main object
                    # if child_node['esphome']['core'] in conditional_nodes:
                    #     config[current_node['id']][current_node['esphome']['automations'][i]]['then'].append({'if': build_conditional_object(config, all_nodes, child_node)})
                    else:
                config[current_node['id']][current_node['esphome']['automations'][i]]['then'].append({f"{child_node['esphome']['core']}.{child_node['esphome']['actions'][0]}": child_id})
                recursive_parse_wires_and_add_to_config(config, all_nodes, child_node)
    # else:
    #     print(current_node)

def get_all_schemas(schema_dir):
    schemas = {}
    schemas_json = os.listdir(schema_dir)
    for schema_filename in schemas_json:
        if (schema_filename.lower().endswith('.json')):
            # with open(os.path.join(os.path.dirname(__file__), configs_dir, filename)) as f:
            with open(os.path.join(schema_dir, schema_filename)) as f:
                schema = json.loads(f.read())
                for component in schema:
                    schemas[component] = schema[component]
                    # if component in debug_schemas_to_collect:
                    #     # print(component)
                    #     schemas[component] = schema[component]
    return schemas

def parse_schemas():
    final_obj = {}
    for component in schemas:
        if 'components' in schemas[component]:
            # this is a core component, and all it's platforms are contained within schemas[component]['components']
            core = schemas[component]
            final_obj[component] = {}
            print(component)
            for platform in core['components']:
                print(f'    {platform}')
                final_obj[component][platform] = {'config_vars': {}, 'automations': {}, 'actions': {}, 'conditions': {}}
                if (component != 'core' and platform != 'xiaomi_miscale2' and platform != 'midea_ac'):
                    add_keys_to_component_obj(final_obj[component][platform], f'{platform}.{component}', 'CONFIG_SCHEMA')
                # skip cores for now, as core.adalight is empty
                # else:
                #     # core is an edge case where the 'platforms' are really base keys, so basically cores
                #     add_keys_to_component_obj(final_obj[component], f'{platform}', 'CONFIG_SCHEMA')
            # print(final_obj[component])
    return final_obj

def add_keys_to_component_obj(component_obj, component_name, config_name):
    # print(component_name, config_name)
    # print(schemas[component_name]['schemas'])
    # TODO binary_sensor_map.sensor has no schema, but weird types
    if schemas[component_name]['schemas'][config_name].get('typed_key'):
        return
    # get actions
    if schemas[component_name].get('action'):
        actions = schemas[component_name]['action']
        for action in actions:
            component_obj['actions'][action] = actions[action]
    # get conditions
    if schemas[component_name].get('condition'):
        conditions = schemas[component_name]['condition']
        for condition in conditions:
            component_obj['conditions'][condition] = conditions[condition]
    schema = schemas[component_name]['schemas'][config_name]['schema']
    if schema.get('extends'):
        for extend in schema['extends']:
            extension = extend.split('.')
            config_name = extension.pop(-1)
            component_name = ''
            for i in range(0, len(extension)):
                if i != 0:
                    component_name += '.'
                component_name += extension[i]
            if (component_name != 'core'): # TODO edge case?
                add_keys_to_component_obj(component_obj, component_name, config_name)
    for var in schema['config_vars']:
        esphome_key = schema['config_vars'][var]
        key_obj = {}
        key = 'automations' if (esphome_key.get('type') == 'trigger') else 'config_vars'
        # if esphome_key.get('schema'):
        #     # this means this is a sub component, so go get modes and type?
        #     print(esphome_key.get('modes'))
        if esphome_key.get('default'):
            key_obj['default'] = esphome_key['default']
        key_obj['required'] = esphome_key.get('key') == 'Required'
        key_obj['id_required'] = (esphome_key.get('id_type') != None)
        if esphome_key.get('docs'):
            key_obj['docs'] = esphome_key['docs']
        component_obj[key][var] = key_obj

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        page = {
            'title': "ESPHome Nodes",
            'favicon': 'favicon.ico',
            'tabicon': {
                'icon': 'red/images/node-red-icon-black.svg',
                'colour': '#8f0000'
            },
            'version': '3.0.0',
            "scripts": [
                "custom/RED.deploy.override.js"
            ]
        }
        asset = {
            'vendorMonaco': 'vendor/monaco/monaco-bootstrap.js',
            'red': 'red/red.min.js',
            'main': 'red/main.min.js'
        }
        with open(os.path.join(os.path.dirname(__file__), editor_client_dir,"templates","index.mst"), 'r') as f:
            self.write(chevron.render(f, {'page':page, 'asset':asset}))

class ThemeHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        self.write(json.dumps({
            "page": {
                "title": "ESPHome Nodes",
                "favicon": "favicon.ico",
                "tabicon": {
                    "icon": "red/images/node-red-icon-black.svg",
                    "colour": "#8f0000"
                },
                "version": "3.0.0",
            },
            "header": {
                "title": "ESPHome Nodes",
                "image": "custom/esphome_logo-text.svg"
            },
            "asset": {
                "red": "red/red.min.js",
                "main": "red/main.min.js",
                "vendorMonaco": "vendor/monaco/monaco-bootstrap.js"
            },
            "themes": []
        }))

class LocalesHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    # TODO handle different languages, just hardcoded "en-US" atm (Maybe not, ESPHome only supports english)
    def get(self, file):
        if file == 'node-red': # nodes specific translations:
            self.write('{}')
            return
        with open(os.path.join(os.path.dirname(__file__), editor_client_dir, "locales", "en-US", f"{file}.json"), 'r') as f:
            self.write(f.read())

class SettingsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        self.write(json.dumps({
            "httpNodeRoot": "/api",
            "version": "3.0.0",
            "context": {
                "default": "memory",
                "stores": [
                    "memory"
                ]
            },
            # Interesting because this is a plugin
            # "libraries": [
            #     {
            #         "id": "local",
            #         "label": "editor:library.types.local",
            #         "user": False,
            #         "icon": "font-awesome/fa-hdd-o"
            #     },
            #     {
            #         "id": "examples",
            #         "label": "editor:library.types.examples",
            #         "user": False,
            #         "icon": "font-awesome/fa-life-ring",
            #         "types": [
            #             "flows"
            #         ],
            #         "readOnly": True
            #     }
            # ],
            "flowEncryptionType": "system",
            "diagnostics": {
                "enabled": True,
                "ui": True
            },
            "runtimeState": {
                "enabled": False,
                "ui": False
            },
            "functionExternalModules": True,
            "tlsConfigDisableLocalFiles": False,
            "paletteCategories": ['subflows', 'core', 'util', 'binary_sensor', 'light'],
            "editorTheme": {
                "languages": [
                    "en-US",
                ],
                'deployButton': {
                    'type':"default",
                    # 'type':"simple",
                    # 'label':"Save",
                    # 'icon': "/absolute/path/to/deploy/button/image" # or null to remove image
                },
                'menu': { # Hide unwanted menu items by id. see packages/node_modules/@node-red/editor-client/src/js/red.js:loadEditor for complete list
                    # "menu-item-import-library": False,
                    # "menu-item-export-library": False,
                    "menu-item-keyboard-shortcuts": False,
                    "menu-item-edit-palette": False,
                    "menu-item-subflow": False,
                    "menu-item-help": False,
                    # "menu-item-help": {
                    #     'label': "Alternative Help Link Text",
                    #     'url': "http://example.com"
                    # }
                },
                'tours': False, # disable the Welcome Tour for new users
                'userMenu': False, # Hide the user-menu even if adminAuth is enabled
                # 'palette': {
                #     editable: true, // *Deprecated* - use externalModules.palette.allowInstall instead
                #     catalogues: [   // Alternative palette manager catalogues
                #         'https://catalogue.nodered.org/catalogue.json'
                #     ],
                #     theme: [ // Override node colours - rules test against category/type by RegExp.
                #         { category: ".*", type: ".*", color: "#f0f" }
                #     ]
                # },
                'projects': {
                    'enabled': False # Enable the projects feature
                },
            }
        }))

class SettingsUserHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        global user
        self.write(json.dumps(user))
    def post(self):
        global user
        user = tornado.escape.json_decode(self.request.body)

class PluginsHandler(tornado.web.RequestHandler):       
    def get(self):
        if (self.request.headers.get("Accept") == "application/json"):
            self.set_header("Content-Type", 'application/json')
            self.write('[]')
        elif (self.request.headers.get("Accept") == "text/html"):
            self.set_header("Content-Type", 'text/html')
            self.write('')

class PluginsMessagesHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        self.write('{}')

class FlowsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        global flows
        self.write(flows)
    def post(self):
        global flows
        global configs_dir
        print(self.request.headers.get('Node-Red-Deployment-Type'))
        flows = tornado.escape.json_decode(self.request.body)
        flows['rev'] = buildRandomHexString(32)
        save_flows_to_file(configs_dir, flows)
        self.write({"rev": flows['rev'] })
        # TODO is this write_message working?       
        if (len(websockets)):
            websockets[0].write_message(json.dumps([{"topic":"notification/runtime-deploy","data":{"revision":flows['rev']}}]))

class NodesHandler(tornado.web.RequestHandler):
    def get(self):
        global nodesObj
        if (self.request.headers.get("Accept") == "application/json"):
            self.set_header("Content-Type", 'application/json')
            # self.write(json.dumps(nodesObj))
            nodes_json = []
            for core in node_schemas:
                for platform in node_schemas[core]:
                    nodes_json.append({
                        "id": f"esphome/{core}.{platform}",
                        "name": f"{core}.{platform}",
                        "types": [
                            f"{core}.{platform}"
                        ],
                        "enabled": True,
                        "local": False,
                        "user": False,
                        "module": "esphome",
                        "version": "3.0.0"
                    })
            for util in util_nodes:
                nodes_json.append({
                    "id": f"esphome/{util}",
                    "name": f"{util}",
                    "types": [
                        f"{util}"
                    ],
                    "enabled": True,
                    "local": False,
                    "user": False,
                    "module": "esphome",
                    "version": "3.0.0"
                })
            self.write(json.dumps(nodes_json))
        elif (self.request.headers.get("Accept") == "text/html"):
            self.set_header("Content-Type", 'text/html')
            # with open(os.path.join(os.path.dirname(__file__), "nodes_html.html"), 'r') as f:
            #     self.write(f.read())
            html = build_component_nodes(node_schemas)
            self.write(html)

class NodesMessagesHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        self.write('{}')

class IconsHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self):
        # TODO build this based on icons in directories and also build an esphome nest as well
        self.write({"node-red":["alert.svg","arduino.png","arrow-in.svg","batch.svg","bluetooth.png","bridge-dash.svg","bridge.svg","cog.svg","comment.svg","db.svg","debug.svg","envelope.svg","feed.svg","file-in.svg","file-out.svg","file.svg","function.svg","hash.svg","inject.svg","join.svg","leveldb.png","light.svg","link-call.svg","link-out.svg","link-return.svg","mongodb.png","mouse.png","parser-csv.svg","parser-html.svg","parser-json.svg","parser-xml.svg","parser-yaml.svg","range.svg","rbe.png","redis.png","rpi.svg","serial.svg","sort.svg","split.svg","status.svg","subflow.svg","swap.svg","switch.svg","template.svg","timer.svg","trigger.svg","watch.svg","white-globe.svg"]})

class CredentialsTabHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')
    def get(self, tab):
        # print(tab)
        # if not doesNodeObjectExistInFlows(flows, 'id', tab):
            # self.write({"flows": flows, "rev": flowRevision })
        self.write('[]')

class CommsSocketHandler(tornado.websocket.WebSocketHandler):
    global websockets
    def check_origin(self, origin):
        return True

    def open(self):
        if self not in websockets:
            websockets.append(self)

    def on_close(self):
        if self in websockets:
            websockets.remove(self)

    def on_message(self, message):
        # print(message)
        if message == '{"subscribe":"notification/runtime-deploy"}':
            self.write_message(json.dumps([{"topic":"notification/runtime-deploy","data":{"revision":flows['rev']}}]))
            # self.write_message(json.dumps([{"topic":"notification/runtime-state","data":{"state":"start"}},{"topic":"notification/runtime-deploy","data":{"revision": flowRevision}}]))

def make_app(relative_url):
    rel = relative_url
    return tornado.web.Application([
        (f"{rel}", MainHandler),
        (f"{rel}theme", ThemeHandler),
        (f"{rel}settings", SettingsHandler),
        (f"{rel}settings/user", SettingsUserHandler),
        (f"{rel}plugins", PluginsHandler),
        (f"{rel}plugins/messages", PluginsMessagesHandler),
        (f"{rel}comms", CommsSocketHandler), # websocket
        (f"{rel}nodes", NodesHandler),
        (f"{rel}nodes/messages", NodesMessagesHandler),
        (f"{rel}flows", FlowsHandler),
        (f"{rel}credentials/tab/(.*)", CredentialsTabHandler),
        (f"{rel}locales/(.*)", LocalesHandler),
        (f"{rel}icons", IconsHandler),
        (f"{rel}custom/(.*)", tornado.web.StaticFileHandler, dict(path=os.path.join(os.path.dirname(__file__), "custom"))),
        (f"{rel}icons/node-red/(.*)", tornado.web.StaticFileHandler, dict(path=os.path.join(os.path.dirname(__file__), "icons"))),
        (f"{rel}(.*)", tornado.web.StaticFileHandler, dict(path=os.path.join(os.path.dirname(__file__), editor_client_dir,"public"))),
    ], debug=True,)

async def main(address, port, esphome_configs_dir):
    global configs_dir
    global schemas
    global node_schemas
    configs_dir = esphome_configs_dir
    get_or_build_flows_file(esphome_configs_dir)
    schemas = get_all_schemas(os.path.join(os.path.dirname(__file__), "schema"))
    node_schemas = parse_schemas()
    # print(node_schemas['stepper'])

    args = {
        'address': address,
        'port': port,
        'relative_url': "/nodes/",
    }
    app = make_app(args['relative_url'])
    print(f"Starting dashboard web server on http://{args['address']}:{args['port']}{args['relative_url']}",)
    app.listen(args['port'])
    # tornado.ioloop.IOLoop.current().start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        if (len(sys.argv)) <= 1:
            print('Please run with a target directory for yaml/flows storage:\n"python3 server.py /dir/of/yaml/and/flows/"')
        asyncio.run(main('localhost',8888, sys.argv[1]))
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")

'''
# for when running within esphome
def start_web_server(args):
    # print(args)
    args = {
        'address': 'localhost',
        'port': '6052',
        'relative_url': "/nodes/",
    }

    global configs_dir
    configs_dir = '/home/callan/git/tmp/node_configs/'
    get_or_build_flows_file('/home/callan/git/tmp/node_configs/')

    # print(a4988.stepper.CONFIG_SCHEMA)
    # print(a4988.CONFIG_SCHEMA)
    app = make_app('/nodes/')
    _LOGGER.info(
        "Starting dashboard web server on http://%s:%s and configuration dir %s...",
        'localhost',
        '6052',
        '/home/callan/git/tmp/node_configs/',
    )
    app.listen('6052', 'localhost')
    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")
'''

# TODO
# start by manually creating simple input and output nodes - boolean input switch and boolean output led
# build special node that should order actions (since we're not thinking 100% linear, ordering a collection of actions is useful)
# override RED.deploy
# load extra JS that adds extra actions using RED.actions.add() (build, upload, run, logs)

# make conditional if, else node
# make a wifi node (investigate a node that has a global presence, like some DB nodes)
