# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: orderer/etcdraft/metadata.proto

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
  name='orderer/etcdraft/metadata.proto',
  package='etcdraft',
  syntax='proto3',
  serialized_pb=_b('\n\x1forderer/etcdraft/metadata.proto\x12\x08\x65tcdraft\"U\n\rBlockMetadata\x12\x15\n\rconsenter_ids\x18\x01 \x03(\x04\x12\x19\n\x11next_consenter_id\x18\x02 \x01(\x04\x12\x12\n\nraft_index\x18\x03 \x01(\x04\"\'\n\x0f\x43lusterMetadata\x12\x14\n\x0c\x61\x63tive_nodes\x18\x01 \x03(\x04\x42j\n.org.hyperledger.fabric.protos.orderer.etcdraftZ8github.com/hyperledger/fabric-protos-go/orderer/etcdraftb\x06proto3')
)




_BLOCKMETADATA = _descriptor.Descriptor(
  name='BlockMetadata',
  full_name='etcdraft.BlockMetadata',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='consenter_ids', full_name='etcdraft.BlockMetadata.consenter_ids', index=0,
      number=1, type=4, cpp_type=4, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='next_consenter_id', full_name='etcdraft.BlockMetadata.next_consenter_id', index=1,
      number=2, type=4, cpp_type=4, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='raft_index', full_name='etcdraft.BlockMetadata.raft_index', index=2,
      number=3, type=4, cpp_type=4, label=1,
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
  serialized_start=45,
  serialized_end=130,
)


_CLUSTERMETADATA = _descriptor.Descriptor(
  name='ClusterMetadata',
  full_name='etcdraft.ClusterMetadata',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='active_nodes', full_name='etcdraft.ClusterMetadata.active_nodes', index=0,
      number=1, type=4, cpp_type=4, label=3,
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
  serialized_start=132,
  serialized_end=171,
)

DESCRIPTOR.message_types_by_name['BlockMetadata'] = _BLOCKMETADATA
DESCRIPTOR.message_types_by_name['ClusterMetadata'] = _CLUSTERMETADATA
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

BlockMetadata = _reflection.GeneratedProtocolMessageType('BlockMetadata', (_message.Message,), dict(
  DESCRIPTOR = _BLOCKMETADATA,
  __module__ = 'orderer.etcdraft.metadata_pb2'
  # @@protoc_insertion_point(class_scope:etcdraft.BlockMetadata)
  ))
_sym_db.RegisterMessage(BlockMetadata)

ClusterMetadata = _reflection.GeneratedProtocolMessageType('ClusterMetadata', (_message.Message,), dict(
  DESCRIPTOR = _CLUSTERMETADATA,
  __module__ = 'orderer.etcdraft.metadata_pb2'
  # @@protoc_insertion_point(class_scope:etcdraft.ClusterMetadata)
  ))
_sym_db.RegisterMessage(ClusterMetadata)


DESCRIPTOR.has_options = True
DESCRIPTOR._options = _descriptor._ParseOptions(descriptor_pb2.FileOptions(), _b('\n.org.hyperledger.fabric.protos.orderer.etcdraftZ8github.com/hyperledger/fabric-protos-go/orderer/etcdraft'))
# @@protoc_insertion_point(module_scope)
