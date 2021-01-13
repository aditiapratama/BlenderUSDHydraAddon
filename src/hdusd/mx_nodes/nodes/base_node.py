#**********************************************************************
# Copyright 2020 Advanced Micro Devices, Inc
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#********************************************************************
import re
from collections import defaultdict

import MaterialX as mx

import bpy
from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    FloatVectorProperty,
    IntVectorProperty,
    BoolProperty,
    PointerProperty,
)

from ...utils import title_str, code_str
from . import log


class MxNodeSocket(bpy.types.NodeSocket):
    bl_idname = 'hdusd.MxNodeSocket'
    bl_label = "MaterialX Node Socket"

    # TODO different type for draw color
    # socket_type: bpy.props.EnumProperty()

    # corresponding property name (if any) on node
    node_prop_name: bpy.props.StringProperty(default='')

    def draw(self, context, layout, node, text):
        # if not linked, we get custom property from the node
        # rather than use the default val like blender sockets
        # this allows custom property UI

        if self.is_linked:
            layout.label(text=self.name)
        else:
            layout.prop(node.prop, self.node_prop_name)

    def draw_color(self, context, node):
        # TODO get from type
        return (0.78, 0.78, 0.16, 1.0)


class MxNodedef(bpy.types.PropertyGroup):
    # holds the materialx nodedef object
    mx_nodedef: mx.NodeDef

    @staticmethod
    def new(mx_nodedef):
        annotations = {}
        for mx_param in mx_nodedef.getParameters():
            prop_name, prop_type, prop_attrs = MxNode.create_property(mx_param)
            annotations['p_' + prop_name] = prop_type, prop_attrs

        for mx_input in mx_nodedef.getInputs():
            prop_name, prop_type, prop_attrs = MxNode.create_property(mx_input)
            annotations['in_' + prop_name] = prop_type, prop_attrs

        for mx_output in mx_nodedef.getOutputs():
            prop_name, prop_type, prop_attrs = MxNode.create_property(mx_output)
            annotations['out_' + prop_name] = prop_type, prop_attrs

        data = {
            'mx_nodedef': mx_nodedef,
            '__annotations__': annotations
        }

        return type('Mx' + mx_nodedef.getName(), (MxNodedef,), data)


class MxNode(bpy.types.ShaderNode):
    """Base node from which all MaterialX nodes will be made"""
    bl_compatibility = {'HdUSD'}
    bl_idname = 'hdusd.MxNode'
    # bl_icon = 'MATERIAL'

    bl_label = ""
    bl_description = ""
    bl_width_default = 250

    mx_nodedefs = ()

    def init(self, context):
        """generates inputs and outputs from ones specified in the mx_nodedef"""
        nd = self.prop.mx_nodedef

        for mx_input in nd.getInputs():
            self.create_input(mx_input)

        for mx_output in nd.getOutputs():
            self.create_output(mx_output)

    def draw_buttons(self, context, layout):
        if len(self.mx_nodedefs) > 1:
            layout.prop(self, 'data_type')

        prop = self.prop
        for mx_param in prop.mx_nodedef.getParameters():
            layout.prop(prop, 'p_' + mx_param.getName())

    # COMPUTE FUNCTION
    def compute(self, out_key, **kwargs):
        def set_value(param, val, nd_type):
            if isinstance(val, mx.Node):
                param.setNodeName(val.getName())
            elif nd_type == 'filename':
                param.setValueString(val)
            else:
                mx_type = getattr(mx, title_str(nd_type), None)
                if mx_type:
                    param.setValue(mx_type(val))
                else:
                    param.setValue(val)

        log("compute", self, out_key)

        doc = kwargs['doc']
        nodedef = self.prop.mx_nodedef
        nd_output = self.get_nodedef_output(out_key)

        values = []
        for in_key in range(len(self.inputs)):
            values.append(self.get_input_value(in_key, **kwargs))

        node = doc.addNode(nodedef.getNodeString(), code_str(self.name), nd_output.getType())
        for in_key, val in enumerate(values):
            nd_input = self.get_nodedef_input(in_key)
            input = node.addInput(nd_input.getName(), nd_input.getType())
            set_value(input, val, nd_input.getType())

        for nd_param in nodedef.getParameters():
            val = self.get_param_value(nd_param.getName())
            param = node.addParameter(nd_param.getName(), nd_param.getType())
            set_value(param, val, nd_param.getType())

        return node

    def _compute_node(self, node, out_key, **kwargs):
        """
        Exports node with output socket.
        1. Checks if such node was already computeed and returns it.
        2. Searches corresponded NodeParser class and do compute through it
        3. Store group node reference if new one passed
        """
        # Keep reference for group node if present
        if not isinstance(node, MxNode):
            log.warn("Ignoring unsupported node", node)
            return None

        # getting corresponded NodeParser class
        return node.compute(out_key, **kwargs)

    def get_input_link(self, in_key: [str, int], **kwargs):
        """Returns linked parsed node or None if nothing is linked or not link is not valid"""

        socket_in = self.inputs[in_key]
        if not socket_in.links:
            return None

        link = socket_in.links[0]
        if not link.is_valid:
            log.error("Invalid link found", link, socket_in, self)

        return self._compute_node(link.from_node, link.from_socket.name, **kwargs)

    def get_input_value(self, in_key: [str, int], **kwargs):
        node = self.get_input_link(in_key, **kwargs)
        if node:
            return node

        return self.get_input_default(in_key)

    def get_input_default(self, in_key: [str, int]):
        return getattr(self.prop, self.inputs[in_key].node_prop_name)

    def get_param_value(self, name):
        return getattr(self.prop, 'p_' + name)

    def get_nodedef_input(self, in_key: [str, int]):
        return self.prop.mx_nodedef.getInput(self.inputs[in_key].node_prop_name[3:])

    def get_nodedef_output(self, out_key: [str, int]):
        return self.prop.mx_nodedef.getOutput(code_str(self.outputs[out_key].name))

    @property
    def prop(self):
        return getattr(self, self.data_type)

    @classmethod
    def poll(cls, tree):
        return tree.bl_idname == 'hdusd.MxNodeTree'

    @staticmethod
    def import_from_mx(nt, mx_node: mx.Node):
        ''' creates a node from a Mx node spec
            sets the params and inputs based on spec '''

        # try:
        #     node_type = 'mx.' + mx_node.getCategory()
        #     blender_node = nt.nodes.new(node_type)
        #     blender_node.label = mx_node.getName()
        #     # get params from
        #     return blender_node
        # except:
        #     # TODO custom nodedefs in file
        #     return None
        pass

    @staticmethod
    def new(nodedef_types):
        mx_nodedefs = tuple(nd_type.mx_nodedef for nd_type in nodedef_types)
        nd = mx_nodedefs[0]
        node_name = nd.getNodeString()

        annotations = {}
        var_items = []
        for nd_type in nodedef_types:
            nd_name = nd_type.mx_nodedef.getName()
            var_name = nd_name[(4 + len(node_name)):]
            annotations[nd_name] = (PointerProperty, {'type': nd_type})
            var_items.append((nd_name, title_str(var_name), title_str(var_name)))

        annotations['data_type'] = (EnumProperty, {
            'name': "Data Type",
            'description': "Input Data Type",
            'items': var_items,
            'default': var_items[0][0],
        })

        data = {
            'bl_label': title_str(nd.getNodeString()),
            'bl_idname': f"{MxNode.bl_idname}_{nd.getName()}",
            'bl_description': nd.getAttribute('doc') if nd.hasAttribute('doc')
                   else title_str(nd.getName()),
            'mx_nodedefs': mx_nodedefs,
            '__annotations__': annotations
        }

        return type('MxNode_' + node_name, (MxNode,), data)

    @staticmethod
    def create_property(mx_param):
        mx_type = mx_param.getType()
        prop_name = mx_param.getName()
        prop_attrs = {}

        while True:     # one way loop just for having break instead using nested 'if else'
            if mx_type == 'string':
                if mx_param.hasAttribute('enum'):
                    prop_type = EnumProperty
                    items = parse_val(prop_type, mx_param.getAttribute('enum'))
                    prop_attrs['items'] = tuple((it, title_str(it), title_str(it))
                                                for it in items)
                    break
                prop_type = StringProperty
                break
            if mx_type == 'filename':
                prop_type = StringProperty
                prop_attrs['subtype'] = 'FILE_PATH'
                break
            if mx_type == 'integer':
                prop_type = IntProperty
                break
            if mx_type == 'float':
                prop_type = FloatProperty
                break
            if mx_type == 'boolean':
                prop_type = BoolProperty
                break
            if mx_type in ('surfaceshader', 'displacementshader', 'volumeshader', 'lightshader',
                           'material', 'BSDF', 'VDF', 'EDF'):
                prop_type = StringProperty
                break

            m = re.fullmatch('matrix(\d)(\d)', mx_type)
            if m:
                prop_type = FloatVectorProperty
                prop_attrs['subtype'] = 'MATRIX'
                prop_attrs['size'] = int(m[1]) * int(m[2])
                break

            m = re.fullmatch('color(\d)', mx_type)
            if m:
                prop_type = FloatVectorProperty
                prop_attrs['subtype'] = 'COLOR'
                prop_attrs['size'] = int(m[1])
                break

            m = re.fullmatch('vector(\d)', mx_type)
            if m:
                prop_type = FloatVectorProperty
                dim = int(m[1])
                prop_attrs['subtype'] = 'XYZ' if dim == 3 else 'NONE'
                prop_attrs['size'] = dim
                break

            m = re.fullmatch('(.+)array', mx_type)
            if m:
                prop_type = StringProperty
                # TODO: Change to CollectionProperty
                break

            prop_type = StringProperty
            log.warn("Unsupported mx_type", mx_type, mx_param, mx_param.getParent().getName())
            break

        prop_attrs['name'] = mx_param.getAttribute('uiname') if mx_param.hasAttribute('uiname')\
            else title_str(prop_name)
        prop_attrs['description'] = mx_param.getAttribute('doc')

        if mx_param.hasAttribute('uimin'):
            prop_attrs['min'] = parse_val(prop_type, mx_param.getAttribute('uimin'), True)
        if mx_param.hasAttribute('uimax'):
            prop_attrs['max'] = parse_val(prop_type, mx_param.getAttribute('uimax'), True)
        if mx_param.hasAttribute('uisoftmin'):
            prop_attrs['soft_min'] = parse_val(prop_type, mx_param.getAttribute('uisoftmin'), True)
        if mx_param.hasAttribute('uisoftmax'):
            prop_attrs['soft_max'] = parse_val(prop_type, mx_param.getAttribute('uisoftmax'), True)

        if mx_param.hasAttribute('value'):
            prop_attrs['default'] = parse_val(prop_type, mx_param.getAttribute('value'),
                                              prop_type == EnumProperty)

        return prop_name, prop_type, prop_attrs

    def create_input(self, mx_input):
        input = self.inputs.new('hdusd.MxNodeSocket',
                                mx_input.getAttribute('uiname') if mx_input.hasAttribute('uiname')
                                else title_str(mx_input.getName()))
        input.node_prop_name = 'in_' + mx_input.getName()
        return input

    def create_output(self, mx_output):
        output = self.outputs.new('NodeSocketShader',
                                  mx_output.getAttribute('uiname') if mx_output.hasAttribute('uiname')
                                  else title_str(mx_output.getName()))
        return output


def parse_val(prop_type, val, first_only=False):
    if prop_type == StringProperty:
        return val
    if prop_type == IntProperty:
        return int(val)
    if prop_type == FloatProperty:
        return float(val)
    if prop_type == BoolProperty:
        return val == "true"
    if prop_type == FloatVectorProperty:
        res = tuple(float(x) for x in val.split(','))
        if first_only:
            return res[0]
        return res
    if prop_type == EnumProperty:
        res = tuple(x.strip() for x in val.split(','))
        if first_only:
            return res[0]
        return res


def create_node_types(file_paths):
    nodedef_types = []
    for p in file_paths:
        doc = mx.createDocument()
        mx.readFromXmlFile(doc, str(p))
        mx_node_defs = doc.getNodeDefs()
        for mx_node_def in mx_node_defs:
            try:
                nodedef_types.append(MxNodedef.new(mx_node_def))
            except Exception as e:
                log.error(mx_node_def.getName(), e)

    # grouping nodedef_types by node and nodegroup
    d = defaultdict(list)
    for nd_type in nodedef_types:
        nd = nd_type.mx_nodedef
        d[(nd.getNodeString(), nd.getAttribute('nodegroup'))].append(nd_type)

    # creating MxNode types
    node_types = []
    for node_name, nd_types in d.items():
        node_types.append(MxNode.new(nd_types))

    return nodedef_types, node_types


class MxNode_Output(MxNode):
    bl_idname = 'hdusd.MxNode_output'
    bl_label = "Material Output"
    bl_description = "Material Output"
    bl_width_default = 150

    def init(self, context):
        self.inputs.new('NodeSocketShader', "Surface")
        self.inputs.new('NodeSocketShader', "Volume")
        self.inputs.new('NodeSocketShader', "Displacement")

    @property
    def prop(self):
        return None

    def draw_buttons(self, context, layout):
        pass

    def compute(self, out_key, **kwargs):
        log("compute", self)

        node = self.get_input_link("Surface", **kwargs)
        if not node:
            return None

        if node.getType() == 'surfaceshader':
            return node

        doc = kwargs['doc']
        surface = doc.addNode('surface', 'surface', 'surfaceshader')
        input = surface.addInput('bsdf', node.getType())
        input.setNodeName(node.getName())

        return surface