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

from pxr import Sdf

from ..utils import logging
log = logging.Log(tag='usd_collection')


COLLECTION_NAME = "USD NodeTree"


def update(context):
    usd_tree_name = context.scene.hdusd.viewport.data_source
    if not usd_tree_name:
        clear(context)
        return

    output_node = bpy.data.node_groups[usd_tree_name].get_output_node()
    if not output_node:
        clear(context)
        return

    stage = output_node.cached_stage()
    if not stage:
        clear(context)
        return

    collection = bpy.data.collections.get(COLLECTION_NAME)
    if not collection:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        context.scene.collection.children.link(collection)
        log("Collection created", collection)

    objects = {}
    for obj in collection.objects:
        if obj.hdusd.is_usd:
            objects[obj.hdusd.sdf_path] = obj
    obj_paths = set(objects.keys())

    prim_paths = set()
    for prim in stage.TraverseAll():
        prim_paths.add(str(prim.GetPath()))

    paths_to_remove = obj_paths - prim_paths
    paths_to_add = prim_paths - obj_paths

    log(f"Removing {len(paths_to_remove)} objects")
    for path in paths_to_remove:
        obj = objects.pop(path)
        bpy.data.objects.remove(obj)

    log(f"Adding {len(paths_to_add)} objects")
    for path in sorted(paths_to_add):
        parent_path = str(Sdf.Path(path).GetParentPath())
        parent_obj = None if parent_path == '/' else objects[parent_path]

        prim = stage.GetPrimAtPath(path)
        obj = bpy.data.objects.new('/', None)
        obj.hdusd.sync_from_prim(parent_obj, prim)
        collection.objects.link(obj)

        objects[path] = obj


def clear(context):
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if not collection:
        return

    log("Removing collection", collection)
    for obj in collection.objects:
        if obj.hdusd.is_usd:
            bpy.data.objects.remove(obj)

    bpy.data.collections.remove(collection)


def scene_save_pre():
    context = bpy.context
    clear(context)


def scene_save_post():
    context = bpy.context
    update(context)