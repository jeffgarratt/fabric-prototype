# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: orderer/configuration.proto

import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
from google.protobuf import descriptor_pb2
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='orderer/configuration.proto',
  package='orderer',
  syntax='proto3',
  serialized_pb=_b('\n\x1borderer/configuration.proto\x12\x07orderer\"\x87\x02\n\rConsensusType\x12\x0c\n\x04type\x18\x01 \x01(\t\x12\x10\n\x08metadata\x18\x02 \x01(\x0c\x12>\n\x0fmigration_state\x18\x03 \x01(\x0e\x32%.orderer.ConsensusType.MigrationState\x12\x19\n\x11migration_context\x18\x04 \x01(\x04\"{\n\x0eMigrationState\x12\x12\n\x0eMIG_STATE_NONE\x10\x00\x12\x13\n\x0fMIG_STATE_START\x10\x01\x12\x14\n\x10MIG_STATE_COMMIT\x10\x02\x12\x13\n\x0fMIG_STATE_ABORT\x10\x03\x12\x15\n\x11MIG_STATE_CONTEXT\x10\x04\"_\n\tBatchSize\x12\x19\n\x11max_message_count\x18\x01 \x01(\r\x12\x1a\n\x12\x61\x62solute_max_bytes\x18\x02 \x01(\r\x12\x1b\n\x13preferred_max_bytes\x18\x03 \x01(\r\"\x1f\n\x0c\x42\x61tchTimeout\x12\x0f\n\x07timeout\x18\x01 \x01(\t\"\x1f\n\x0cKafkaBrokers\x12\x0f\n\x07\x62rokers\x18\x01 \x03(\t\"(\n\x13\x43hannelRestrictions\x12\x11\n\tmax_count\x18\x01 \x01(\x04\x42U\n%org.hyperledger.fabric.protos.ordererZ,github.com/hyperledger/fabric/protos/ordererb\x06proto3')
)



_CONSENSUSTYPE_MIGRATIONSTATE = _descriptor.EnumDescriptor(
  name='MigrationState',
  full_name='orderer.ConsensusType.MigrationState',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='MIG_STATE_NONE', index=0, number=0,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='MIG_STATE_START', index=1, number=1,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='MIG_STATE_COMMIT', index=2, number=2,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='MIG_STATE_ABORT', index=3, number=3,
      options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='MIG_STATE_CONTEXT', index=4, number=4,
      options=None,
      type=None),
  ],
  containing_type=None,
  options=None,
  serialized_start=181,
  serialized_end=304,
)
_sym_db.RegisterEnumDescriptor(_CONSENSUSTYPE_MIGRATIONSTATE)


_CONSENSUSTYPE = _descriptor.Descriptor(
  name='ConsensusType',
  full_name='orderer.ConsensusType',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='type', full_name='orderer.ConsensusType.type', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='metadata', full_name='orderer.ConsensusType.metadata', index=1,
      number=2, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=_b(""),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='migration_state', full_name='orderer.ConsensusType.migration_state', index=2,
      number=3, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='migration_context', full_name='orderer.ConsensusType.migration_context', index=3,
      number=4, type=4, cpp_type=4, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _CONSENSUSTYPE_MIGRATIONSTATE,
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=41,
  serialized_end=304,
)


_BATCHSIZE = _descriptor.Descriptor(
  name='BatchSize',
  full_name='orderer.BatchSize',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='max_message_count', full_name='orderer.BatchSize.max_message_count', index=0,
      number=1, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='absolute_max_bytes', full_name='orderer.BatchSize.absolute_max_bytes', index=1,
      number=2, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='preferred_max_bytes', full_name='orderer.BatchSize.preferred_max_bytes', index=2,
      number=3, type=13, cpp_type=3, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=306,
  serialized_end=401,
)


_BATCHTIMEOUT = _descriptor.Descriptor(
  name='BatchTimeout',
  full_name='orderer.BatchTimeout',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='timeout', full_name='orderer.BatchTimeout.timeout', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=403,
  serialized_end=434,
)


_KAFKABROKERS = _descriptor.Descriptor(
  name='KafkaBrokers',
  full_name='orderer.KafkaBrokers',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='brokers', full_name='orderer.KafkaBrokers.brokers', index=0,
      number=1, type=9, cpp_type=9, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=436,
  serialized_end=467,
)


_CHANNELRESTRICTIONS = _descriptor.Descriptor(
  name='ChannelRestrictions',
  full_name='orderer.ChannelRestrictions',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='max_count', full_name='orderer.ChannelRestrictions.max_count', index=0,
      number=1, type=4, cpp_type=4, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=469,
  serialized_end=509,
)

_CONSENSUSTYPE.fields_by_name['migration_state'].enum_type = _CONSENSUSTYPE_MIGRATIONSTATE
_CONSENSUSTYPE_MIGRATIONSTATE.containing_type = _CONSENSUSTYPE
DESCRIPTOR.message_types_by_name['ConsensusType'] = _CONSENSUSTYPE
DESCRIPTOR.message_types_by_name['BatchSize'] = _BATCHSIZE
DESCRIPTOR.message_types_by_name['BatchTimeout'] = _BATCHTIMEOUT
DESCRIPTOR.message_types_by_name['KafkaBrokers'] = _KAFKABROKERS
DESCRIPTOR.message_types_by_name['ChannelRestrictions'] = _CHANNELRESTRICTIONS
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

ConsensusType = _reflection.GeneratedProtocolMessageType('ConsensusType', (_message.Message,), dict(
  DESCRIPTOR = _CONSENSUSTYPE,
  __module__ = 'orderer.configuration_pb2'
  # @@protoc_insertion_point(class_scope:orderer.ConsensusType)
  ))
_sym_db.RegisterMessage(ConsensusType)

BatchSize = _reflection.GeneratedProtocolMessageType('BatchSize', (_message.Message,), dict(
  DESCRIPTOR = _BATCHSIZE,
  __module__ = 'orderer.configuration_pb2'
  # @@protoc_insertion_point(class_scope:orderer.BatchSize)
  ))
_sym_db.RegisterMessage(BatchSize)

BatchTimeout = _reflection.GeneratedProtocolMessageType('BatchTimeout', (_message.Message,), dict(
  DESCRIPTOR = _BATCHTIMEOUT,
  __module__ = 'orderer.configuration_pb2'
  # @@protoc_insertion_point(class_scope:orderer.BatchTimeout)
  ))
_sym_db.RegisterMessage(BatchTimeout)

KafkaBrokers = _reflection.GeneratedProtocolMessageType('KafkaBrokers', (_message.Message,), dict(
  DESCRIPTOR = _KAFKABROKERS,
  __module__ = 'orderer.configuration_pb2'
  # @@protoc_insertion_point(class_scope:orderer.KafkaBrokers)
  ))
_sym_db.RegisterMessage(KafkaBrokers)

ChannelRestrictions = _reflection.GeneratedProtocolMessageType('ChannelRestrictions', (_message.Message,), dict(
  DESCRIPTOR = _CHANNELRESTRICTIONS,
  __module__ = 'orderer.configuration_pb2'
  # @@protoc_insertion_point(class_scope:orderer.ChannelRestrictions)
  ))
_sym_db.RegisterMessage(ChannelRestrictions)


DESCRIPTOR.has_options = True
DESCRIPTOR._options = _descriptor._ParseOptions(descriptor_pb2.FileOptions(), _b('\n%org.hyperledger.fabric.protos.ordererZ,github.com/hyperledger/fabric/protos/orderer'))
# @@protoc_insertion_point(module_scope)
