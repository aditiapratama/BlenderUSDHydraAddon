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
import bpy


class HdUSD_Panel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    COMPAT_ENGINES = {'HdUSD'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


from . import (
    panels,
    render,
    light,
    material,
    usd_list,
)


register_classes, unregister_classes = bpy.utils.register_classes_factory([
    render.HDUSD_OP_render_source_select,
    render.HDUSD_MT_render_source,
    render.HDUSD_RENDER_PT_delegate_final,
    render.HDUSD_RENDER_PT_delegate_viewport,

    light.HDUSD_LIGHT_PT_light,

    material.HDUSD_MATERIAL_PT_context,
    material.HDUSD_MATERIAL_PT_preview,
    material.HDUSD_MATERIAL_PT_surface,
    material.HDUSD_MATERIAL_PT_displacement,
    material.HDUSD_MATERIAL_PT_volume,

    usd_list.HDUSD_OP_usd_list_item_expand,
    usd_list.HDUSD_OP_usd_list_item_show_hide,
    usd_list.HDUSD_UL_usd_list_item,
    usd_list.HDUSD_NODE_PT_usd_list,
    usd_list.HDUSD_OP_usd_nodetree_add_basic_nodes,
    usd_list.HDUSD_NODE_PT_usd_nodetree_operations,
])


def register():
    panels.register()
    register_classes()


def unregister():
    panels.unregister()
    unregister_classes()
