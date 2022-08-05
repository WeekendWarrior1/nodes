import random
# import chevron        # moustache templating is just too limited
import os
from jinja2 import Environment, BaseLoader

def random_colour():
    # https://stackoverflow.com/a/18035471
    # return "#%06x" % random.randint(0, 0xFFFFFF)
    return "#%06x" % random.randint(0x666666, 0xFFFFFF)

def build_component_nodes(node_schemas):
    nodes_render_data = []

    for core in node_schemas:
        for platform in node_schemas[core]:
            nodes_render_data.append(build_node_render_obj(core, platform, node_schemas[core][platform]))
    
    with open(os.path.join('/home/callan/git/weekendwarrior1/nodes',"nodes_template.jinja"), 'r') as nodes_template:
        # # TODO clean up just sticking static html on end of file, should be done with jinja
        with open(os.path.join('/home/callan/git/weekendwarrior1/nodes',"util_nodes.html"), 'r') as util_nodes:
            rtemplate = Environment(loader=BaseLoader()).from_string(nodes_template.read())
            return(rtemplate.render(**{'nodes': nodes_render_data}) + util_nodes.read())

def build_node_render_obj(core, platform, schema):
    config_vars = schema['config_vars']
    automations = schema['automations']
    actions = schema['actions']
    conditions = schema['conditions']

    config_vars_keys = list(config_vars.keys())
    automations_keys = list(automations.keys())
    actions_keys = list(actions.keys())
    conditions_keys = list(conditions.keys())
    required = []
    optional = []
    all_config_vars = []
    for key in config_vars:
        attrs = { 'name': key } # TODO can I use name for this key? I think so
        for attr in config_vars[key]:
            attrs[attr] = config_vars[key][attr]
        if attr == 'docs':
            if len(config_vars[key][attr].split('**')) > 1:
                attrs['data_type'] = config_vars[key][attr].split('**')[1]
        if attrs.get('required') == True:
            required.append(attrs)
        else:
            optional.append(attrs)
        all_config_vars.append(attrs)

    docs_strings = []
    # for key in (config_vars + automations):
    for key in config_vars:
        if config_vars[key].get('docs'):
            docs_strings.append(config_vars[key]['docs'])
    for key in automations:
        if automations[key].get('docs'):
            docs_strings.append(automations[key]['docs'])

    render_obj = {
        'core': core,
        'platform': platform,
        'schema': config_vars_keys,
        'required': required,
        'optional': optional,
        'all_config_vars': all_config_vars,
        'docs': docs_strings,
        'hex_colour': random_colour(),
        'automations': automations_keys,
        'automations_length': len(automations_keys),
        'actions': actions_keys,
        'actions_length': len(actions_keys),
        'conditions': conditions_keys,
        'conditions_length': len(conditions_keys),
    }
    if len(required):
        render_obj['required_exists'] = True
    if len(optional):
        render_obj['optional_exists'] = True

    return render_obj