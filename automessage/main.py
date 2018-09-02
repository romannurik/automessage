# Copyright 2018 Google Inc.
#
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

import calendar
import datetime
import sys

import protorpc.definition
import protorpc.descriptor

from google.appengine.ext import ndb
from google.appengine.ext.ndb import msgprop


_SERIALIZERS_BY_MSG_CLS = {}
_DESERIALIZERS_BY_MSG_CLS = {}
_MSG_CLASSES_BY_MODEL_CLS = {}


def populate(model_cls, **kwargs):
  '''Decorator on a messages.Message subclass that populates it with fields from the given
  model class.'''

  _prepare_model_class(model_cls)

  def _decorator(target_cls):
    return _make_message_class(target_cls.__name__, target_cls.__module__, model_cls, **kwargs)

  return _decorator


def attach(name=None, **kwargs):
  '''Decorator on a ndb.Model subclass that creates and registers a messages.Message subclass
  for it in the same module.'''

  def _decorator(model_cls):
    _prepare_model_class(model_cls)
    _name = name
    if not _name:
      _name = '%sMessage' % model_cls.__name__
    message_cls = _make_message_class(_name, model_cls.__module__, model_cls, **kwargs)
    setattr(sys.modules[model_cls.__module__], _name, message_cls)
    return model_cls

  return _decorator



def _make_message_class(target_name, target_module_name, model_cls,
                        id_field=False, camel_case=False, types={},
                        only_props=[], exclude_props=[]):
  only_props = set(only_props)
  exclude_props = set(exclude_props)
  msg_prop_name = lambda prop_name: prop_name
  if camel_case:
    msg_prop_name = (lambda v:
                     v.split('_')[0] + ''.join(x.capitalize() or '_' for x in v.split('_')[1:]))

  fields = []
  field_number = 0
  message_types = []

  prop_serializers = {}
  prop_deserializers = {}

  # add ID field
  if id_field:
    field_number += 1
    fields.append(protorpc.descriptor.FieldDescriptor(
        name=msg_prop_name('id'),
        number=field_number,
        label=protorpc.descriptor.FieldDescriptor.Label.OPTIONAL,
        variant=protorpc.descriptor.FieldDescriptor.Variant.UINT64))
    prop_serializers['id'] = lambda entity, prop_name: entity.key.id()
    # prop_deserializers[prop_name] = prop_deserializer

  # list all properties
  for (prop_name, prop) in model_cls._properties.items():
    if len(only_props) and not prop_name in only_props:
      continue
    if len(exclude_props) and prop_name in exclude_props:
      continue

    field_number += 1

    # determine label (options)
    label = protorpc.descriptor.FieldDescriptor.Label.OPTIONAL
    if prop._repeated:
      label = protorpc.descriptor.FieldDescriptor.Label.REPEATED
    elif prop._required:
      label = protorpc.descriptor.FieldDescriptor.Label.REQUIRED

    # determine variant (data type) and create from/to converters
    variant = None
    attrs = dict()

    prop_serializer = lambda entity, prop_name: getattr(entity, prop_name)
    prop_deserializer = lambda message, prop_name: getattr(message, msg_prop_name(prop_name))

    if type(prop) == ndb.IntegerProperty:
      variant = protorpc.descriptor.FieldDescriptor.Variant.INT64

    elif type(prop) == ndb.FloatProperty:
      variant = protorpc.descriptor.FieldDescriptor.Variant.DOUBLE

    elif type(prop) == ndb.BooleanProperty:
      variant = protorpc.descriptor.FieldDescriptor.Variant.BOOL

    elif (type(prop) == ndb.StringProperty or
          type(prop) == ndb.TextProperty):
      variant = protorpc.descriptor.FieldDescriptor.Variant.STRING

    elif type(prop) == ndb.BlobProperty:
      variant = protorpc.descriptor.FieldDescriptor.Variant.BYTES

    elif type(prop) == msgprop.EnumProperty:
      variant = protorpc.descriptor.FieldDescriptor.Variant.ENUM
      attrs['type_name'] = prop._enum_type.__module__ + '.' + prop._enum_type.__name__

    elif type(prop) == ndb.DateTimeProperty:
      # TODO: handle Date, and Time properties
      # TODO: look into use DateTimeField somehow
      variant = protorpc.descriptor.FieldDescriptor.Variant.UINT64
      def _dt_serializer(entity, prop_name):
        dt = getattr(entity, prop_name)
        return calendar.timegm(dt.utctimetuple()) * 1000 if dt else None # TODO: need to do much more here
      prop_serializer = _dt_serializer
      def _dt_deserializer(message, prop_name):
        timestamp = getattr(message, msg_prop_name(prop_name))
        return datetime.datetime.fromtimestamp(timestamp / 1000) if timestamp else None
      prop_deserializer = _dt_deserializer

    elif (type(prop) == ndb.StructuredProperty or
          type(prop) == ndb.LocalStructuredProperty):
      variant = protorpc.descriptor.FieldDescriptor.Variant.MESSAGE
      prop_message_cls = None
      if prop._modelclass in types:
        prop_message_cls = types[prop._modelclass]
      else:
        if prop._modelclass in _MSG_CLASSES_BY_MODEL_CLS:
          msg_classes = _MSG_CLASSES_BY_MODEL_CLS[prop._modelclass]
          if len(msg_classes) > 1:
            raise TypeError(('More than one message type is defined for entity class %s; you ' +
                              'must pass in a message type in "types"') % prop._modelclass.__name__)
          prop_message_cls = msg_classes[0]
        else:
          raise TypeError('No message type defined for entity class %s' % prop._modelclass.__name__)

      attrs['type_name'] = prop_message_cls.__module__ + '.' + prop_message_cls.__name__
      if prop._repeated:
        prop_serializer = (lambda entity, prop_name:
            [_message_from_entity(sub_entity, prop_message_cls)
              for sub_entity in getattr(entity, prop_name)])
        prop_deserializer = (lambda message, prop_name:
            [_entity_from_message(sub_message)
              for sub_message in getattr(message, msg_prop_name(prop_name))])
      else:
        prop_serializer = (lambda entity, prop_name:
            _message_from_entity(getattr(entity, prop_name), prop_message_cls))
        prop_deserializer = (lambda message, prop_name:
            _entity_from_message(getattr(message, msg_prop_name(prop_name))))
      # TODO: need to generate a message class for this model class type
      #message_types.append(protorpc.descriptor.describe_message(prop_message_cls))
      #raise NotImplementedError('Structured properties must be in "types"')

    else:
      # ndb.GeoPtProperty	Geographical location. This is a ndb.GeoPt object. The object has attributes lat and lon, both floats. You can construct one with two floats like ndb.GeoPt(52.37, 4.88) or with a string ndb.GeoPt("52.37, 4.88"). (This is actually the same class as db.GeoPt)
      # ndb.KeyProperty	Cloud Datastore key
      # ndb.BlobKeyProperty	Blobstore key
      # ndb.UserProperty	User object.
      # ndb.JsonProperty	Value is a Python object (such as a list or a dict or a string) that is serializable using Python's json module; Cloud Datastore stores the JSON serialization as a blob. Unindexed by default.
      # ndb.GenericProperty	Generic value
      # ndb.ComputedProperty
      raise NotImplementedError('No matching message variant for type %s' % type(prop).__name__)

    prop_serializers[prop_name] = prop_serializer
    prop_deserializers[prop_name] = prop_deserializer

    # TODO: handle default values?

    # create the field description
    fields.append(protorpc.descriptor.FieldDescriptor(
        name=msg_prop_name(prop_name),
        number=field_number,
        label=label,
        variant=variant,
        **attrs))

  # create the new class
  message_cls = protorpc.definition.define_message(
      protorpc.descriptor.MessageDescriptor(
        name=target_name,
        fields=fields,
        message_types=message_types), # add enum_types for nested definitions
      target_module_name)

  # add from/to conversion
  def _serializer(entity):
    new_message = message_cls()
    for (prop_name, serializer) in prop_serializers.items():
      setattr(new_message, msg_prop_name(prop_name), serializer(entity, prop_name))
    return new_message

  def _deserializer(message, update_entity = None):
    entity = update_entity if update_entity else model_cls()
    for (prop_name, deserializer) in prop_deserializers.items():
      setattr(entity, prop_name, deserializer(message, prop_name))
    return entity

  _DESERIALIZERS_BY_MSG_CLS[message_cls] = _deserializer
  _SERIALIZERS_BY_MSG_CLS[message_cls] = _serializer

  if not model_cls in _MSG_CLASSES_BY_MODEL_CLS:
    _MSG_CLASSES_BY_MODEL_CLS[model_cls] = []
  _MSG_CLASSES_BY_MODEL_CLS[model_cls].append(message_cls)

  return message_cls


def _prepare_model_class(model_cls):
  setattr(model_cls, 'to_message', _message_from_entity)
  model_cls.from_message = staticmethod(_entity_from_message)


def _message_from_entity(entity, message_cls=None):
  if not message_cls:
    model_cls = entity.__class__
    if model_cls in _MSG_CLASSES_BY_MODEL_CLS:
      msg_classes = _MSG_CLASSES_BY_MODEL_CLS[model_cls]
      if len(msg_classes) > 1:
        raise TypeError(('More than one message type is defined for entity class %s; you ' +
                         'must pass in a message type to serialize to') % model_cls.__name__)
      message_cls = msg_classes[0]
    else:
      raise TypeError('No message type defined for entity class %s' % model_cls.__name__)

  if message_cls in _SERIALIZERS_BY_MSG_CLS:
    return _SERIALIZERS_BY_MSG_CLS[message_cls](entity)

  raise TypeError('Message class %s doesn\'t have a from-entity converter' % message_cls.__name__)


def _entity_from_message(message, update_entity=None):
  message_cls = message.__class__
  if message_cls in _DESERIALIZERS_BY_MSG_CLS:
    return _DESERIALIZERS_BY_MSG_CLS[message_cls](message, update_entity)

  raise TypeError('Message class %s doesn\'t have a to-entity converter' % message_cls.__name__)
