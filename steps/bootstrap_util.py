# Copyright IBM Corp. 2016 All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import time
import sys
import hashlib
import uuid

if sys.version_info < (3, 6):
    import sha3

from OpenSSL import crypto
import ecdsa
from asn1crypto.core import Sequence, Integer, OctetString

from collections import namedtuple
from itertools import groupby
from concurrent.futures import ThreadPoolExecutor

from enum import Enum

from google.protobuf import timestamp_pb2
from common import common_pb2 as common_dot_common_pb2
from common import configtx_pb2 as common_dot_configtx_pb2
from common import configuration_pb2 as common_dot_configuration_pb2
from common import policies_pb2 as common_dot_policies_pb2
from msp import msp_config_pb2, msp_principal_pb2, identities_pb2
from peer import configuration_pb2 as peer_dot_configuration_pb2
from orderer import configuration_pb2 as orderer_dot_configuration_pb2
from orderer.etcdraft import configuration_pb2 as orderer_dot_etcdraft_dot_configuration_pb2
import orderer_util
from bdd_test_util import cli_call

from contexthelper import ContextHelper

import os
import re
import shutil
import compose

# Type to represent tuple of user, nodeName, ogranization
NodeAdminTuple = namedtuple("NodeAdminTuple", ['user', 'nodeName', 'organization'])


ApplicationGroup = "Application"
OrdererGroup     = "Orderer"
ConsortiumsGroup = "Consortiums"
MSPKey           = "MSP"
toValue = lambda message: message.SerializeToString()


class Network(Enum):
    Orderer = 1
    Peer = 2


def GetUUID():
    return compose.Composition.GetUUID()

def GetUniqueChannelName():
    while True:
        guiid = uuid.uuid4().hex[:6].lower()
        if guiid[:1].isalpha():
            break
    return guiid

def createRSAKey():
    # Create RSA key, 2048 bit
    pk = crypto.PKey()
    pk.generate_key(crypto.TYPE_RSA, 2048)
    assert pk.check() == True
    return pk


def createECDSAKey(curve=ecdsa.NIST256p):
    # Create ECDSA key
    sk = ecdsa.SigningKey.generate(curve=curve)
    return sk


def calculate_ski_per_sdk_node(public_key):
    # uncompressed point (https://www.security-audit.com/files/x9-62-09-20-98.pdf, section 4.3.6)
    part1 = bytearray()
    part1.append(4)
    # Now part 2, the public key
    part2 = ecdsa.VerifyingKey.from_pem(crypto.dump_publickey(crypto.FILETYPE_PEM, public_key)).to_string()
    # Construct the full byte array
    data = bytearray().join([part1, part2])
    return computeCryptoHash(data).encode('hex')

def computeCryptoHash(data):
    ' This will currently return 128 hex characters'
    # s = hashlib.sha3_256()
    s = hashlib.sha256()
    # s = hashlib.shake_256()
    #return s.digest(64)
    s.update(data)
    return s.digest()


def createCertRequest(pkey, extensions=[], digest="sha256", **name):
    """
    Create a certificate request.
    Arguments: pkey   - The key to associate with the request
               digest - Digestion method to use for signing, default is sha256
               **name - The name of the subject of the request, possible
                        arguments are:
                          C     - Country name
                          ST    - State or province name
                          L     - Locality name
                          O     - Organization name
                          OU    - Organizational unit name
                          CN    - Common name
                          emailAddress - E-mail address
    Returns:   The certificate request in an X509Req object
    """
    req = crypto.X509Req()
    subj = req.get_subject()

    for key, value in name.items():
        setattr(subj, key, value)

    req.add_extensions(extensions)

    req.set_pubkey(pkey)
    req.sign(pkey, digest)
    return req


def createCertificate(req, issuerCertKey, serial, validityPeriod, digest="sha256", isCA=False, extensions=[]):
    """
    Generate a certificate given a certificate request.
    Arguments: req        - Certificate request to use
               issuerCert - The certificate of the issuer
               issuerKey  - The private key of the issuer
               serial     - Serial number for the certificate
               notBefore  - Timestamp (relative to now) when the certificate
                            starts being valid
               notAfter   - Timestamp (relative to now) when the certificate
                            stops being valid
               digest     - Digest method to use for signing, default is sha256
    Returns:   The signed certificate in an X509 object
    """
    issuerCert, issuerKey = issuerCertKey
    notBefore, notAfter = validityPeriod
    cert = crypto.X509()
    cert.set_version(2)
    cert.set_serial_number(serial)
    cert.gmtime_adj_notBefore(notBefore)
    cert.gmtime_adj_notAfter(notAfter)
    cert.set_issuer(issuerCert.get_subject())
    cert.set_subject(req.get_subject())
    cert.set_pubkey(req.get_pubkey())
    if isCA:
        cert.add_extensions([crypto.X509Extension("basicConstraints", True,
                                                  "CA:TRUE, pathlen:0"),
                             crypto.X509Extension("subjectKeyIdentifier", False, "hash",
                                                  subject=cert)])
        #TODO: This only is appropriate for root self signed!!!!
        cert.add_extensions([crypto.X509Extension("authorityKeyIdentifier", False, "keyid:always", issuer=cert)])
    else:
        cert.add_extensions([crypto.X509Extension("basicConstraints", True,
                                                  "CA:FALSE"),
                             crypto.X509Extension("subjectKeyIdentifier", False, "hash",
                                                  subject=cert)])
        cert.add_extensions([crypto.X509Extension("authorityKeyIdentifier", False, "keyid:always", issuer=issuerCert)])

    cert.add_extensions(extensions)
    cert.sign(issuerKey, digest)
    return cert


# SUBJECT_DEFAULT = {countryName : "US", stateOrProvinceName : "NC", localityName : "RTP", organizationName : "IBM", organizationalUnitName : "Blockchain"}

class Entity:
    def __init__(self, name, ecdsaSigningKey, rsaSigningKey):
        self.name = name
        # Create a ECDSA key, then a crypto pKey from the DER for usage with cert requests, etc.
        self.ecdsaSigningKey = ecdsaSigningKey
        self.rsaSigningKey = rsaSigningKey
        if self.ecdsaSigningKey:
            self.pKey = crypto.load_privatekey(crypto.FILETYPE_ASN1, self.ecdsaSigningKey.to_der())
        # Signing related ecdsa config
        self.hashfunc = hashlib.sha256
        self.sigencode = ecdsa.util.sigencode_der_canonize
        self.sigdecode = ecdsa.util.sigdecode_der

    def createCertRequest(self, nodeName, extensions = []):
        req = createCertRequest(self.pKey, extensions=extensions, C="US", ST="North Carolina", L="RTP", O="IBM", CN=nodeName)
        return req

    def createTLSCertRequest(self, nodeName):
        req = createCertRequest(self.rsaSigningKey, C="US", ST="North Carolina", L="RTP", O="IBM", CN=nodeName)
        # print("request => {0}".format(crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)))
        return req


    def computeHash(self, data):
        s = self.hashfunc()
        s.update(data)
        return s.digest()

    def sign(self, dataAsBytearray):
        return self.ecdsaSigningKey.sign(dataAsBytearray, hashfunc=self.hashfunc, sigencode=self.sigencode)

    def verifySignature(self, signature, signersCert, data):
        'Will verify the signature of an entity based upon public cert'
        vk = ecdsa.VerifyingKey.from_der(crypto.dump_publickey(crypto.FILETYPE_ASN1, signersCert.get_pubkey()))
        assert vk.verify(signature, data, hashfunc=self.hashfunc, sigdecode=self.sigdecode), "Invalid signature!!"

    def getPrivateKeyAsPEM(self):
        return self.ecdsaSigningKey.to_pem()

    def __getstate__(self):
        state = dict(self.__dict__)
        del state['ecdsaSigningKey']
        del state['rsaSigningKey']
        del state['pKey']
        return state

class User(Entity, orderer_util.UserRegistration):
    def __init__(self, name, directory, ecdsaSigningKey, rsaSigningKey):
        Entity.__init__(self, name, ecdsaSigningKey=ecdsaSigningKey, rsaSigningKey=rsaSigningKey)
        orderer_util.UserRegistration.__init__(self, name, directory)
        self.tags = {}

    def setTagValue(self, tagKey, tagValue, overwrite=False):
        if tagKey in self.tags:
            if not overwrite:
                raise Exception("TagKey '{0}' already exists for user {1}, and did not provide overwrite=True".format(tagKey, self.getUserName()))
        self.tags[tagKey] = tagValue
        return tagValue

    def getTagValue(self, tagKey):
        return self.tags[tagKey]

    def cleanup(self):
        self.closeStreams()


class Organization(Entity):

    def __init__(self, name, ecdsaSigningKey, rsaSigningKey):
        Entity.__init__(self, name, ecdsaSigningKey, rsaSigningKey)
        req = createCertRequest(self.pKey, C="US", ST="North Carolina", L="RTP", O="IBM", CN=name)
        numYrs = 1
        self.signedCert = createCertificate(req, (req, self.pKey), 1000, (0, 60 * 60 * 24 * 365 * numYrs), isCA=True)
        # Which networks this organization belongs to
        self.networks = []

    def __repr__(self):
        return "name:{0}, networks: {1}".format(self.name, self.networks)

    def getSelfSignedCert(self):
        return self.signedCert

    def getCertAsPEM(self):
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.getSelfSignedCert())

    def isInNetwork(self, network):
        for n in self.networks:
            if str(n)==str(network):
                return True
        return False

    def getMspPrincipalAsRole(self, mspRoleTypeAsString):
        mspRole = msp_principal_pb2.MSPRole(msp_identifier=self.name, role=msp_principal_pb2.MSPRole.MSPRoleType.Value(mspRoleTypeAsString))
        mspPrincipal = msp_principal_pb2.MSPPrincipal(
            principal_classification=msp_principal_pb2.MSPPrincipal.Classification.Value('ROLE'),
            principal=mspRole.SerializeToString())
        return mspPrincipal

    def createCertificate(self, certReq, extensions=[]):
        numYrs = 1
        return createCertificate(certReq, (self.signedCert, self.pKey), 1000, (0, 60 * 60 * 24 * 365 * numYrs), extensions=extensions)

    def addToNetwork(self, network):
        'Used to track which network this organization is defined in.'
        # assert network in Network, 'Network not recognized ({0}), expected to be one of ({1})'.format(network, list(Network))
        if not network in self.networks:
            self.networks.append(network)


class Directory:
    def __init__(self):
        import atexit
        self.organizations = {}
        self.users = {}
        self.ordererAdminTuples = {}
        atexit.register(self.cleanup)

    def getNamedCtxTuples(self):
        return self.ordererAdminTuples

    def _registerOrg(self, orgName):
        assert orgName not in self.organizations, "Organization already registered {0}".format(orgName)
        self.organizations[orgName] = Organization(orgName, ecdsaSigningKey = createECDSAKey(), rsaSigningKey = createRSAKey())
        return self.organizations[orgName]

    def _registerUser(self, userName):
        assert userName not in self.users, "User already registered {0}".format(userName)
        self.users[userName] = User(userName, directory=self, ecdsaSigningKey = createECDSAKey(), rsaSigningKey = createRSAKey())
        return self.users[userName]

    def getUser(self, userName, shouldCreate=False):
        if not userName in self.users and shouldCreate:
            # self.users[userName] = User(userName)
            self._registerUser(userName)
        return self.users[userName]

    def getUsers(self):
        return self.users

    def cleanup(self):
        '''Perform cleanup of resources'''
        [user.cleanup() for user in self.users.values()]

    def getOrganization(self, orgName, shouldCreate=False):
        if not orgName in self.organizations and shouldCreate:
            # self.organizations[orgName] = Organization(orgName)
            self._registerOrg(orgName)
        return self.organizations[orgName]

    def getOrganizations(self):
        return self.organizations

    def findCertByTuple(self, userName, contextName, orgName):
        ordererAdminTuple = NodeAdminTuple(user=userName, nodeName=contextName, organization=orgName)
        return self.ordererAdminTuples[ordererAdminTuple]

    def findCertForNodeAdminTuple(self, nodeAdminTuple):
        assert nodeAdminTuple in self.ordererAdminTuples, "Node admin tuple not found for: {0}".format(nodeAdminTuple)
        return self.ordererAdminTuples[nodeAdminTuple]

    def getCertAsPEM(self, nodeAdminTuple):
        assert nodeAdminTuple in self.ordererAdminTuples, "Node admin tuple not found for: {0}".format(nodeAdminTuple)
        return crypto.dump_certificate(crypto.FILETYPE_PEM, self.ordererAdminTuples[nodeAdminTuple])

    def findNodeAdminTuple(self, userName, contextName, orgName):
        nodeAdminTuple = NodeAdminTuple(user=userName, nodeName=contextName, organization=orgName)
        assert nodeAdminTuple in self.ordererAdminTuples, "Node admin tuple not found for: {0}".format(nodeAdminTuple)
        return nodeAdminTuple

    def getTrustedRootsForPeerNetworkAsPEM(self):
        pems = [peerOrg.getCertAsPEM() for peerOrg in [org for org in self.getOrganizations().values() if org.isInNetwork(Network.Peer)]]
        return "".join(pems)

    def getTrustedRootsForOrdererNetworkAsPEM(self):
        pems = [ordererOrg.getCertAsPEM() for ordererOrg in [org for org in self.getOrganizations().values() if org.isInNetwork(Network.Orderer)]]
        return "".join(pems)


    def _get_cert_extensions_ip_sans(self, user_name, node_name):
        extensions = []
        if 'signer' in user_name.lower():
            if ('peer' in node_name.lower() or 'orderer' in node_name.lower()):
                san_list = ["DNS:{0}".format(node_name)]
                extensions.append(crypto.X509Extension(b"subjectAltName", False, ", ".join(san_list)))
        return extensions

    def registerOrdererAdminTuple(self, userName, ordererName, organizationName):
        ' Assign the user as orderer admin'
        ordererAdminTuple = NodeAdminTuple(user=userName, nodeName=ordererName, organization=organizationName)
        assert ordererAdminTuple not in self.ordererAdminTuples, "Orderer admin tuple already registered {0}".format(
            ordererAdminTuple)
        assert organizationName in self.organizations, "Orderer Organization not defined {0}".format(organizationName)

        user = self.getUser(userName, shouldCreate=True)
        # Add the subjectAlternativeName if the current entity is a signer, and the nodeName contains peer or orderer
        extensions = self._get_cert_extensions_ip_sans(userName, ordererName)
        certReq = user.createCertRequest(ordererAdminTuple.nodeName, extensions=extensions)
        userCert = self.getOrganization(organizationName).createCertificate(certReq, extensions=extensions)

        # Verify the newly created certificate
        store = crypto.X509Store()
        # Assuming a list of trusted certs
        for trustedCert in [self.getOrganization(organizationName).signedCert]:
            store.add_cert(trustedCert)
        # Create a certificate context using the store and the certificate to verify
        store_ctx = crypto.X509StoreContext(store, userCert)
        # Verify the certificate, returns None if it can validate the certificate
        store_ctx.verify_certificate()
        self.ordererAdminTuples[ordererAdminTuple] = userCert
        return ordererAdminTuple

    def dump(self, output):
        'Will dump the directory to the provided store'
        import cPickle
        data = {'users' : {}, 'organizations' : {}, 'nats' : {}}
        dump_cert = lambda cert: crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
        for userName, user in self.users.iteritems():
            # for k, v in user.tags.iteritems():
            #     try:
            #         cPickle.dumps(v)
            #     except:
            #         raise Exception("Failed on key {0}".format(k))
            data['users'][userName] = (user.ecdsaSigningKey.to_pem(), crypto.dump_privatekey(crypto.FILETYPE_PEM, user.rsaSigningKey), user.tags)
        for orgName, org in self.organizations.iteritems():
            networks = [n.name for n in  org.networks]
            data['organizations'][orgName] = (
                org.ecdsaSigningKey.to_pem(), crypto.dump_privatekey(crypto.FILETYPE_PEM, org.rsaSigningKey),
                dump_cert(org.getSelfSignedCert()), networks)
        for nat, cert in self.ordererAdminTuples.iteritems():
            data['nats'][nat] = dump_cert(cert)
        cPickle.dump(data, output)

    def initFromPath(self, path):
        'Will initialize the directory from the path supplied'
        import cPickle
        data = None
        with open(path,'r') as f:
            data = cPickle.load(f)
        assert data != None, "Expected some data, did not load any."
        priv_key_from_pem = lambda x: crypto.load_privatekey(crypto.FILETYPE_PEM, x)
        for userName, keyTuple in data['users'].iteritems():
            self.users[userName] = User(userName, directory=self,
                                        ecdsaSigningKey=ecdsa.SigningKey.from_pem(keyTuple[0]),
                                        rsaSigningKey=priv_key_from_pem(keyTuple[1]))
            self.users[userName].tags = keyTuple[2]
        for orgName, tuple in data['organizations'].iteritems():
            org = Organization(orgName, ecdsaSigningKey=ecdsa.SigningKey.from_pem(tuple[0]),
                               rsaSigningKey=priv_key_from_pem(tuple[1]))
            org.signedCert = crypto.load_certificate(crypto.FILETYPE_PEM, tuple[2])
            org.networks = [Network[name] for name in tuple[3]]
            self.organizations[orgName] = org
        for nat, cert_as_pem in data['nats'].iteritems():
            self.ordererAdminTuples[nat] = crypto.load_certificate(crypto.FILETYPE_PEM, cert_as_pem)

    def find_config_admins_for_org(self, org):
        # Find the mspAdmin Tuple for org, returns (nodeAdminTupe, cert) tuple list
        return [(nat, cert) for nat, cert in self.ordererAdminTuples.items() if
                org.name == nat.organization and "configadmin" in nat.nodeName.lower()]


class AuthDSLHelper:
    @classmethod
    def Envelope(cls, signaturePolicy, identities):
        'Envelope builds an envelope message embedding a SignaturePolicy'
        return common_dot_policies_pb2.SignaturePolicyEnvelope(
            version=0,
            rule=signaturePolicy,
            identities=identities)

    @classmethod
    def NOutOf(cls, n, policies):
        'NOutOf creates a policy which requires N out of the slice of policies to evaluate to true'
        return common_dot_policies_pb2.SignaturePolicy(
            n_out_of=common_dot_policies_pb2.SignaturePolicy.NOutOf(
                n=n,
                rules=policies,
            ),
        )

    @classmethod
    def SignedBy(cls, index):
        'NOutOf creates a policy which requires N out of the slice of policies to evaluate to true'
        return common_dot_policies_pb2.SignaturePolicy(
            signed_by=index
        )

    @classmethod
    def Member(cls, organization):
        return organization.getMspPrincipalAsRole(mspRoleTypeAsString='MEMBER')

class PolicyParser:

    def __init__(self, directory):
        self.directory = directory

    def member(self, org_name):
        org = self.directory.getOrganization(orgName=org_name)
        return AuthDSLHelper.Member(organization=org)

    def parse(self, policy_string):
        n_out_of = AuthDSLHelper.NOutOf
        signed_by = AuthDSLHelper.SignedBy
        member = self.member
        envelope = AuthDSLHelper.Envelope
        result = None
        exec('result = ' + policy_string)
        return result

def make_signature_header(serializeCertChain, nonce):
    return common_dot_common_pb2.SignatureHeader(creator=serializeCertChain,
                                                     nonce=nonce)

def get_timestamp():
    return timestamp_pb2.Timestamp(seconds=int(time.time()), nanos=0)

def make_chain_header(type, channel_id, txID="", extension='', version=1,
                      timestamp_func=get_timestamp,
                      epoch=0):
    return common_dot_common_pb2.ChannelHeader(type=type,
                                               version=version,
                                               timestamp=timestamp_func(),
                                               channel_id=channel_id,
                                               epoch=epoch,
                                               tx_id=txID,
                                               extension=extension)


class ServiceStopped:
    def __init__(self, composition, compose_service):
        self.composition = composition
        self.compose_service = compose_service
    def __enter__(self):
        self.composition.issueCommand(['stop'],[self.compose_service])
        return (self.composition, self.compose_service)
    def __exit__(self, type, value, traceback):
        self.composition.issueCommand(['start'],[self.compose_service])


class ServicesStoppedAndReadyForSnapshot:
    def __init__(self, callback_helper, snapshot_name, composition, compose_services, snapshot_folder_exist, stop_wait_interval=0):
        self.callback_helper = callback_helper
        self.composition = composition
        self.compose_services = compose_services
        self.snapshot_folder_exist = snapshot_folder_exist
        self.snapshot_name = snapshot_name
        self.stop_wait_interval = stop_wait_interval

    def __enter__(self):
        for compose_service in self.compose_services:
            assert compose_service in self.callback_helper.get_service_list(composition=self.composition), "Compose service not found: {0}".format(compose_service)
            # Check it the snapshot path existence expectation is met
            snapshot_path = self.callback_helper.get_snapshot_path(project_name=self.composition.projectName, compose_service=compose_service, snapshot=self.snapshot_name)
            assert self.snapshot_folder_exist == os.path.exists(snapshot_path), "Expected the snapshot folder to {0}exist: {1}".format("" if self.snapshot_folder_exist else "NOT ", snapshot_path)
        for compose_service in self.compose_services:
            self.composition.issueCommand(['stop'],[compose_service])
            time.sleep(self.stop_wait_interval)
        return self
    def __exit__(self, type, value, traceback):
        for compose_service in self.compose_services:
            self.composition.issueCommand(['start'],[compose_service])



class BootstrapHelper:

    class BlockHeaderSequence(Sequence):
        """ASN.1 Structure for BlockHeader.  Used for computation of Block hash."""
        _fields = [
            ('Number', Integer),
            ('PreviousHash', OctetString),
            ('DataHash', OctetString),
        ]

    def compute_block_hash(self, block):
        """Computes the Hash of the given block."""
        bhs = BootstrapHelper.BlockHeaderSequence({'Number' : block.header.number, 'PreviousHash': block.header.previous_hash,'DataHash': block.header.data_hash})
        return computeCryptoHash(bhs.dump())

    def compute_block_data_hash(self, block_data):
        """Computes the Hash of the given BlockData."""
        return computeCryptoHash("".join(block_data.data))

    def verify_block(self, block):
        """Verifies a block.  NOTE: Currently does NOT verify all of the signatures"""
        assert self.compute_block_data_hash(block.data) == block.header.data_hash, "Hash of block.data does NOT match block.header.data_hash"

    KEY_CONSENSUS_TYPE = "ConsensusType"
    KEY_ORDERER_KAFKA_BROKERS = "KafkaBrokers"
    KEY_CHAIN_CREATION_POLICY_NAMES = "ChainCreationPolicyNames"
    KEY_CHANNEL_CREATION_POLICY = "ChannelCreationPolicy"
    KEY_CHANNEL_RESTRICTIONS = "ChannelRestrictions"
    KEY_CONSORTIUM = "Consortium"
    KEY_ACCEPT_ALL_POLICY = "AcceptAllPolicy"
    KEY_HASHING_ALGORITHM = "HashingAlgorithm"
    KEY_BLOCKDATA_HASHING_STRUCTURE = "BlockDataHashingStructure"
    KEY_BATCH_SIZE = "BatchSize"
    KEY_BATCH_TIMEOUT = "BatchTimeout"
    KEY_CREATIONPOLICY = "CreationPolicy"
    KEY_MSP_INFO = "MSP"
    KEY_ANCHOR_PEERS = "AnchorPeers"

    KEY_NEW_CONFIGURATION_ITEM_POLICY = "NewConfigurationItemPolicy"
    DEFAULT_CHAIN_CREATORS = [KEY_ACCEPT_ALL_POLICY]

    # ReadersPolicyKey is the key used for the read policy
    KEY_POLICY_READERS = "Readers"
    # WritersPolicyKey is the key used for the writer policy
    KEY_POLICY_WRITERS = "Writers"
    # AdminsPolicyKey is the key used for the admins policy
    KEY_POLICY_ADMINS = "Admins"

    KEY_POLICY_BLOCK_VALIDATION = "BlockValidation"

    # OrdererAddressesKey is the cb.ConfigItem type key name for the OrdererAddresses message
    KEY_ORDERER_ADDRESSES = "OrdererAddresses"

    # Key for capabilities
    KEY_CAPABILITIES = "Capabilities"

    DEFAULT_NONCE_SIZE = 24

    @classmethod
    def getNonce(cls):
        # return rand.bytes(BootstrapHelper.DEFAULT_NONCE_SIZE)
        return os.urandom(BootstrapHelper.DEFAULT_NONCE_SIZE)

    def add_signature_to_config_update_envelope(self, configUpdateEnvelope, (entity, mspId, cert)):
        serializedIdentity = identities_pb2.SerializedIdentity(mspid=mspId, id_bytes=crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        sigHeader = common_dot_common_pb2.SignatureHeader(creator=serializedIdentity.SerializeToString(),
                                                          nonce=BootstrapHelper.getNonce())
        sigHeaderBytes = sigHeader.SerializeToString()
        # Signature over the concatenation of configurationItem bytes and signatureHeader bytes
        signature = entity.sign(sigHeaderBytes + configUpdateEnvelope.config_update)
        # Now add new signature to Signatures repeated field
        newConfigSig = configUpdateEnvelope.signatures.add()
        newConfigSig.signature_header = sigHeaderBytes
        newConfigSig.signature = signature

    def __init__(self, lastModified=0, msgVersion=1, epoch=0, consensusType="solo", batchSize=10,
                 batchTimeout=".5s", absoluteMaxBytes=100000000, preferredMaxBytes=512 * 1024, signers=[]):
        self.lastModified = lastModified
        self.msgVersion = msgVersion
        self.epoch = epoch
        self.consensusType = consensusType
        self.batchSize = batchSize
        self.batchTimeout = batchTimeout
        self.absoluteMaxBytes = absoluteMaxBytes
        self.preferredMaxBytes = preferredMaxBytes
        self.signers = signers

    def create_genesis_block(self, context, service_names, chainId, consensusType, nodeAdminTuple, signedConfigItems=[]):
        'Generates the genesis block for starting the oderers and for use in the chain config transaction by peers'
        # assert not "bootstrapGenesisBlock" in context,"Genesis block already created:\n{0}".format(context.bootstrapGenesisBlock)
        directory = getDirectory(context)
        assert len(directory.ordererAdminTuples) > 0, "No orderer admin tuples defined!!!"

        channelConfig = self.create_channel_config_group(context = context, directory=directory, service_names=service_names, consensusType=consensusType)
        for configGroup in signedConfigItems:
            merge_config_groups(channelConfig, configGroup)

        config = common_dot_configtx_pb2.Config(
            sequence=0,
            channel_group=channelConfig)

        configEnvelope = common_dot_configtx_pb2.ConfigEnvelope(config=config)
        envelope = create_envelope_for_msg(directory=directory, chainId=chainId, nodeAdminTuple=nodeAdminTuple, msg=configEnvelope, typeAsString="CONFIG")
        blockData = common_dot_common_pb2.BlockData(data=[envelope.SerializeToString()])

        # Spoke with kostas, for orderer in general
        signaturesMetadata = ""
        lastConfigurationBlockMetadata = common_dot_common_pb2.Metadata(
            value=common_dot_common_pb2.LastConfig(index=0).SerializeToString()).SerializeToString()
        ordererConfigMetadata = ""
        transactionFilterMetadata = ""
        bootstrapHelper = BootstrapHelper()
        block = common_dot_common_pb2.Block(
            header=common_dot_common_pb2.BlockHeader(
                number=0,
                previous_hash=None,
                data_hash=bootstrapHelper.compute_block_data_hash(blockData),
            ),
            data=blockData,
            metadata=common_dot_common_pb2.BlockMetadata(
                metadata=[signaturesMetadata, lastConfigurationBlockMetadata, transactionFilterMetadata,
                          ordererConfigMetadata]),
        )

        # Add this back once crypto certs are required
        for nodeAdminTuple in directory.ordererAdminTuples:
            userCert = directory.ordererAdminTuples[nodeAdminTuple]
            certAsPEM = crypto.dump_certificate(crypto.FILETYPE_PEM, userCert)
            # print("UserCert for orderer genesis:\n{0}\n".format(certAsPEM))
            # print("")

        return (block, envelope, channelConfig)

    def create_channel_config_group(self, context, directory, service_names, hashingAlgoName="SHA256", consensusType="solo", batchTimeout="1s", batchSizeMaxMessageCount=10, batchSizeAbsoluteMaxBytes=100000000, batchSizePreferredMaxBytes=512 * 1024, channel_max_count=0):

        channel = common_dot_configtx_pb2.ConfigGroup()
        # channel.groups[ApplicationGroup] = common_dot_configtx_pb2.ConfigGroup()
        # channel.groups[OrdererGroup] = common_dot_configtx_pb2.ConfigGroup()
        # channel.groups[ApplicationGroup]
        channel.groups[OrdererGroup]
        # v = common_dot_configtx_pb2.ConfigItem.ConfigType.Value
        # configItems.append(bootstrapHelper.encodeHashingAlgorithm())
        channel.values[BootstrapHelper.KEY_HASHING_ALGORITHM].value = toValue(
            common_dot_configuration_pb2.HashingAlgorithm(name=hashingAlgoName))

        golangMathMaxUint32 = 4294967295
        channel.values[BootstrapHelper.KEY_BLOCKDATA_HASHING_STRUCTURE].value = toValue(
            common_dot_configuration_pb2.BlockDataHashingStructure(width=golangMathMaxUint32))


        if consensusType == "etcdraft":
            # Build the Consenters
            options = orderer_dot_etcdraft_dot_configuration_pb2.Options(tick_interval="500ms",
                                                                         election_tick=10,
                                                                         heartbeat_tick=1,
                                                                         max_inflight_blocks=5,
                                                                         snapshot_interval_size=10 * 1024 * 1024)
            configMetadata = orderer_dot_etcdraft_dot_configuration_pb2.ConfigMetadata(options=options)

            composition = context.composition
            orderer_callback_helper = composition.GetCallbackInContextByDiscriminator(context, OrdererGensisBlockCompositionCallback.DISCRIMINATOR)
            assert orderer_callback_helper, "No Orderer callback helper currently registered in context"
            for orderer_service_name in [service_name for service_name in service_names if "orderer" in service_name]:
                consenter = configMetadata.consenters.add()
                consenter.host = orderer_service_name
                consenter.port = 7050
                (_, pnt) = orderer_callback_helper._getPathAndUserInfo(directory=directory, project_name=composition.projectName, compose_service=orderer_service_name, pathType=PathType.Container)
                (keyPath, certPath) = orderer_callback_helper.getTLSKeyPaths(pnt=pnt, project_name=composition.projectName, compose_service=orderer_service_name, pathType=PathType.Container)
                with open(certPath, 'r') as f:
                    cert = f.read()
                    consenter.client_tls_cert = cert
                    consenter.server_tls_cert = cert
                # org = directory.getOrganization(pnt.organization)
                # org_cert_as_pem = org.getCertAsPEM()
                # consenter.client_tls_cert = org_cert_as_pem
                # consenter.server_tls_cert = org_cert_as_pem
            channel.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE].value = toValue(orderer_dot_configuration_pb2.ConsensusType(type=consensusType, metadata=toValue(configMetadata)))
        else:
            channel.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE].value = toValue(orderer_dot_configuration_pb2.ConsensusType(type=consensusType))

        channel.groups[OrdererGroup].values[BootstrapHelper.KEY_BATCH_SIZE].value = toValue(orderer_dot_configuration_pb2.BatchSize(max_message_count=batchSizeMaxMessageCount,absolute_max_bytes=batchSizeAbsoluteMaxBytes,preferred_max_bytes=batchSizePreferredMaxBytes))
        channel.groups[OrdererGroup].values[BootstrapHelper.KEY_BATCH_TIMEOUT].value = toValue(orderer_dot_configuration_pb2.BatchTimeout(timeout=batchTimeout))
        channel.groups[OrdererGroup].values[BootstrapHelper.KEY_CHANNEL_RESTRICTIONS].value = toValue(orderer_dot_configuration_pb2.ChannelRestrictions(max_count=channel_max_count))


        acceptAllPolicy = common_dot_policies_pb2.Policy(type=1, value=AuthDSLHelper.Envelope(
            signaturePolicy=AuthDSLHelper.NOutOf(0, []), identities=[]).SerializeToString())
        # channel.policies[BootstrapHelper.KEY_ACCEPT_ALL_POLICY].policy.CopyFrom(acceptAllPolicy)

        # For now, setting same policies for each 'Non-Org' group
        typeImplicitMeta = common_dot_policies_pb2.Policy.PolicyType.Value("IMPLICIT_META")
        Policy = common_dot_policies_pb2.Policy
        IMP = common_dot_policies_pb2.ImplicitMetaPolicy
        ruleAny = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("ANY")
        ruleMajority = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("MAJORITY")
        for group in [channel, channel.groups[OrdererGroup]]:
            group.policies[BootstrapHelper.KEY_POLICY_READERS].policy.CopyFrom(Policy(type=typeImplicitMeta, value=IMP(
                rule=ruleAny, sub_policy=BootstrapHelper.KEY_POLICY_READERS).SerializeToString()))
            group.policies[BootstrapHelper.KEY_POLICY_WRITERS].policy.CopyFrom(Policy(type=typeImplicitMeta, value=IMP(
                rule=ruleAny, sub_policy=BootstrapHelper.KEY_POLICY_WRITERS).SerializeToString()))
            group.policies[BootstrapHelper.KEY_POLICY_ADMINS].policy.CopyFrom(Policy(type=typeImplicitMeta, value=IMP(
                rule=ruleMajority, sub_policy=BootstrapHelper.KEY_POLICY_ADMINS).SerializeToString()))
            for pKey, pVal in group.policies.iteritems():
                pVal.mod_policy = BootstrapHelper.KEY_POLICY_ADMINS
            group.mod_policy = BootstrapHelper.KEY_POLICY_ADMINS

        # Setting block validation policy for the orderer group
        channel.groups[OrdererGroup].policies[BootstrapHelper.KEY_POLICY_BLOCK_VALIDATION].policy.CopyFrom(Policy(type=typeImplicitMeta, value=IMP(
            rule=ruleAny, sub_policy=BootstrapHelper.KEY_POLICY_WRITERS).SerializeToString()))
        channel.groups[OrdererGroup].policies[BootstrapHelper.KEY_POLICY_BLOCK_VALIDATION].mod_policy=BootstrapHelper.KEY_POLICY_ADMINS

        # Add the orderer org groups MSPConfig info
        for ordererOrg in [org for org in directory.getOrganizations().values() if org.isInNetwork(Network.Orderer)]:
            channel.groups[OrdererGroup].groups[ordererOrg.name].values[BootstrapHelper.KEY_MSP_INFO].value = toValue(
                get_msp_config(org=ordererOrg, directory=directory))
            channel.groups[OrdererGroup].groups[ordererOrg.name].values[BootstrapHelper.KEY_MSP_INFO].mod_policy=BootstrapHelper.KEY_POLICY_ADMINS

        #Kafka specific
        kafka_brokers = ["{0}:9092".format(service_name) for service_name in service_names if "kafka" in service_name]
        if len(kafka_brokers) > 0:
            channel.groups[OrdererGroup].values[BootstrapHelper.KEY_ORDERER_KAFKA_BROKERS].value = toValue(
                orderer_dot_configuration_pb2.KafkaBrokers(brokers=kafka_brokers))

        for vKey, vVal in channel.groups[OrdererGroup].values.iteritems():
            vVal.mod_policy=BootstrapHelper.KEY_POLICY_ADMINS



        # Now set policies for each org group (Both peer and orderer)
        #TODO: Revisit after Jason does a bit more refactoring on chain creation policy enforcement
        ordererOrgs = [o for o in directory.getOrganizations().values() if o.isInNetwork(Network.Orderer)]
        set_default_policies_for_orgs(channel, ordererOrgs, OrdererGroup, version=0, policy_version=0)

        #New OrdererAddress
        ordererAddress = common_dot_configuration_pb2.OrdererAddresses()
        for orderer_service_name in [service_name for service_name in service_names if "orderer" in service_name]:
            ordererAddress.addresses.append("{0}:7050".format(orderer_service_name))
        assert len(ordererAddress.addresses) > 0, "No orderer nodes were found while trying to create channel ConfigGroup"
        channel.values[BootstrapHelper.KEY_ORDERER_ADDRESSES].value = toValue(ordererAddress)


        for pKey, pVal in channel.values.iteritems():
            pVal.mod_policy = BootstrapHelper.KEY_POLICY_ADMINS


        return channel


    def add_capabilities(self, config_group, capabilities_to_add, mod_policy="Admins", increment_new_group_version=True, increment_value_version=True, fail_if_exists=True):
        # First create a copy to return (does NOT alter the supplied messages)
        new_config_group = common_dot_configtx_pb2.ConfigGroup()
        new_config_group.CopyFrom(config_group)

        #Must increment the version of the group as the cardinality of a member is changing
        if increment_new_group_version:
            new_config_group.version +=1

        # Increment the version if required
        if BootstrapHelper.KEY_CAPABILITIES in new_config_group.values:
            if increment_value_version:
                new_config_group.values[BootstrapHelper.KEY_CAPABILITIES].version +=1
        else:
            # Newly created, set the appropriate mod_policy and version
            new_config_group.values[BootstrapHelper.KEY_CAPABILITIES].mod_policy = mod_policy
            new_config_group.values[BootstrapHelper.KEY_CAPABILITIES].version = 0

        # Get the current capabilities
        capabilities = common_dot_configuration_pb2.Capabilities()
        capabilities.ParseFromString(new_config_group.values[BootstrapHelper.KEY_CAPABILITIES].value)

        # Make sure does NOT already exist
        for new_capabilitiy in capabilities_to_add:
            if fail_if_exists:
                assert not new_capabilitiy in capabilities.capabilities, 'Capability already exist: {0}'.format(new_capabilitiy)
            # Now add
            capabilities.capabilities[new_capabilitiy]
        new_config_group.values[BootstrapHelper.KEY_CAPABILITIES].value = capabilities.SerializeToString()
        return new_config_group

    def create_capabilities_config_update(self, channel_id, config_group, group_to_capabilities_to_add):
        'Creates the config update and adds capabilities specified'

        read_set = common_dot_configtx_pb2.ConfigGroup()
        write_set = common_dot_configtx_pb2.ConfigGroup()

        read_set.CopyFrom(config_group)
        write_set.CopyFrom(read_set)

        # Loop through each group and add capabilities
        for group_path, capabilities in group_to_capabilities_to_add.iteritems():
            config_group_to_add_to = self.get_group_from_config_path(config_group=write_set, config_path=group_path)
            new_config_group = self.add_capabilities(config_group=config_group_to_add_to, capabilities_to_add=capabilities)
            config_group_to_add_to.CopyFrom(new_config_group)

        config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=channel_id, read_set=read_set, write_set=write_set)

        return config_update

    def get_group_from_config_path(self, config_group, config_path):
        current_config_group = config_group
        assert config_path.split('/')[1]=='Channel', 'Expected /Channel to start config path, instead found {0}'.format(config_path)
        for group_id in config_path.split('/')[2:]:
            assert group_id in current_config_group.groups.keys(), "Key not found in config group {0}, path specified was {1}".format(group_id, config_path)
            current_config_group = current_config_group.groups[group_id]
        return current_config_group

    def _orderer_system_snapshot_template_method(self, method_name, orderers, context, composition, snapshot_name, snapshot_folder_exist):
        'Performs the provided snapshot method for the orderer system.'
        orderer_callback_helper = composition.GetCallbackInContextByDiscriminator(context, OrdererGensisBlockCompositionCallback.DISCRIMINATOR)
        assert orderer_callback_helper, "No Orderer callback helper currently registered in context"
        with ServicesStoppedAndReadyForSnapshot(callback_helper=orderer_callback_helper, snapshot_name=snapshot_name,
                                                composition=composition, compose_services=orderers,
                                                snapshot_folder_exist=snapshot_folder_exist) as ctxMgr:
            for compose_service in ctxMgr.compose_services:
                func = getattr(orderer_callback_helper, method_name)
                func(project_name=composition.projectName, compose_service=compose_service, snapshot=snapshot_name)
            # Now stop the Kafka servers slowly to allow for leader changes during shutdown, then snapshot
            kafka_callback_helper = composition.GetCallbackInContextByDiscriminator(context, KafkaCompositionCallback.DISCRIMINATOR)
            if kafka_callback_helper:
                with ServicesStoppedAndReadyForSnapshot(callback_helper=kafka_callback_helper, snapshot_name=snapshot_name,
                                                        composition=composition, compose_services=kafka_callback_helper.get_service_list(composition),
                                                        snapshot_folder_exist=snapshot_folder_exist,
                                                        stop_wait_interval=KafkaCompositionCallback.REPLICA_HIGH_WATERMARK_CHECKPOINT_INTERVAL_MS / 1000) as kafkaCtxMgr:
                    for compose_service in kafkaCtxMgr.compose_services:
                        func = getattr(kafka_callback_helper, method_name)
                        func(project_name=composition.projectName, compose_service=compose_service, snapshot=snapshot_name)

    def snapshot_orderer_system(self, context, composition, snapshot_name):
        'Snapshots the orderer system.  This was a pre Raft system operation, as before raft, it only made sense to snapshot the entire system.'
        orderer_callback_helper = composition.GetCallbackInContextByDiscriminator(context, OrdererGensisBlockCompositionCallback.DISCRIMINATOR)
        assert orderer_callback_helper, "No Orderer callback helper currently registered in context"
        all_orderers=orderer_callback_helper.get_service_list(composition=composition)
        self._orderer_system_snapshot_template_method(method_name="snapshot_filestore", orderers=all_orderers, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=False)


    def restore_orderer_system_using_snapshot(self, context, composition, snapshot_name):
        'Restores the orderer system using a supplied snapshot name.'
        orderer_callback_helper = composition.GetCallbackInContextByDiscriminator(context, OrdererGensisBlockCompositionCallback.DISCRIMINATOR)
        assert orderer_callback_helper, "No Orderer callback helper currently registered in context"
        all_orderers=orderer_callback_helper.get_service_list(composition=composition)
        self._orderer_system_snapshot_template_method(method_name="restore_filestore_snapshot", orderers=all_orderers, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=True)

    def snapshot_orderers(self, orderers_to_snapshot, context, composition, snapshot_name):
        'Snapshots the supplied orderers.'
        self._orderer_system_snapshot_template_method(method_name="snapshot_filestore", orderers=orderers_to_snapshot, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=False)

    def restore_orderers_using_snapshot(self, orderers_to_restore, context, composition, snapshot_name):
        'Restores the specified orderers system using a supplied snapshot name.'
        self._orderer_system_snapshot_template_method(method_name="restore_filestore_snapshot", orderers=orderers_to_restore, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=True)

    def _snapshot_peer(self, peer_callback_helper, method_name, compose_service, context, composition, snapshot_name, composition_config_as_yaml):
        'Performs the provided snapshot method for the peer compose_service provided.'
        func = getattr(peer_callback_helper, method_name)
        func(project_name=composition.projectName, compose_service=compose_service, snapshot=snapshot_name)

        # See if this peer has a dependent couchdb service
        couchdb_service = peer_callback_helper.get_couchdb_service_for_peer(compose_service=compose_service, composition_config_as_yaml=composition_config_as_yaml)
        if couchdb_service:
            # Now stop the associated couchdb server and snapshot
            couchdb_callback_helper = composition.GetCallbackInContextByDiscriminator(context, CouchDBCompositionCallback.DISCRIMINATOR)
            assert couchdb_callback_helper, "No CouchDB callback helper currently registered in context"
            # Now stop the couchdb servers
            with ServiceStopped(composition=composition, compose_service=couchdb_service):
                func = getattr(couchdb_callback_helper, method_name)
                func(project_name=composition.projectName, compose_service=couchdb_service, snapshot=snapshot_name)

    def _snapshot_peers_template_method(self, method_name, peers, context, composition, snapshot_name, snapshot_folder_exist):
        'Performs the provided snapshot method for the peers list provided.'
        import yaml
        peer_callback_helper = composition.GetCallbackInContextByDiscriminator(context, PeerCompositionCallback.DISCRIMINATOR)
        assert peer_callback_helper, "No Peer callback helper currently registered in context"
        config = yaml.load(composition.getConfig())
        with ServicesStoppedAndReadyForSnapshot(callback_helper=peer_callback_helper, snapshot_name=snapshot_name, composition=composition, compose_services=peers, snapshot_folder_exist=snapshot_folder_exist) as ctxMgr:
            with ThreadPoolExecutor(max_workers=len(ctxMgr.compose_services)) as executor:
                [executor.submit(self._snapshot_peer, peer_callback_helper, method_name,
                                 compose_service, context, composition,
                                 snapshot_name, config) for compose_service in ctxMgr.compose_services]

    def snapshot_peers(self, peers_to_snapshot, context, composition, snapshot_name):
        'Snapshots the list of peer service names provided.'
        self._snapshot_peers_template_method(method_name="snapshot_filestore", peers=peers_to_snapshot, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=False)

    def restore_peers_using_snapshot(self, peers_to_restore, context, composition, snapshot_name):
        'Restore from snapshots the list of peer service names provided.'
        self._snapshot_peers_template_method(method_name="restore_filestore_snapshot", peers=peers_to_restore, context=context, composition=composition, snapshot_name=snapshot_name, snapshot_folder_exist=True)


def getDirectory(context):
    if 'bootstrapDirectory' not in context:
        context.bootstrapDirectory = Directory()
    return context.bootstrapDirectory


def getOrdererBootstrapAdmin(context, shouldCreate=False):
    directory = getDirectory(context)
    ordererBootstrapAdmin = directory.getUser(userName="ordererBootstrapAdmin", shouldCreate=shouldCreate)
    return ordererBootstrapAdmin


def addOrdererBootstrapAdminOrgReferences(context, policyName, orgNames):
    'Adds a key/value pair of policyName/[orgName,...]'
    directory = getDirectory(context)
    ordererBootstrapAdmin = directory.getUser(userName="ordererBootstrapAdmin", shouldCreate=False)
    if not 'OrgReferences' in ordererBootstrapAdmin.tags:
        ordererBootstrapAdmin.tags['OrgReferences'] = {}
    policyNameToOrgNamesDict = ordererBootstrapAdmin.tags['OrgReferences']
    assert not policyName in policyNameToOrgNamesDict, "PolicyName '{0}' already registered with ordererBootstrapAdmin".format(
        policyName)
    policyNameToOrgNamesDict[policyName] = orgNames
    return policyNameToOrgNamesDict


def getOrdererBootstrapAdminOrgReferences(context):
    directory = getDirectory(context)
    ordererBootstrapAdmin = directory.getUser(userName="ordererBootstrapAdmin", shouldCreate=False)
    if not 'OrgReferences' in ordererBootstrapAdmin.tags:
        ordererBootstrapAdmin.tags['OrgReferences'] = {}
    return ordererBootstrapAdmin.tags['OrgReferences']

def getAnchorPeersConfigGroup(context, nodeAdminTuples, peer_port=7051, mod_policy=BootstrapHelper.KEY_POLICY_ADMINS):
    directory = getDirectory(context)
    config_group = common_dot_configtx_pb2.ConfigGroup()
    for orgName, group in groupby([(nat.organization, nat) for nat in nodeAdminTuples], lambda x: x[0]):
        anchorPeers = peer_dot_configuration_pb2.AnchorPeers()
        for (k,nodeAdminTuple) in group:
            anchorPeer = anchorPeers.anchor_peers.add()
            anchorPeer.host = nodeAdminTuple.nodeName
            anchorPeer.port = peer_port
            # anchorPeer.cert = crypto.dump_certificate(crypto.FILETYPE_PEM,
            #                                           directory.findCertForNodeAdminTuple(nodeAdminTuple))
        config_group.groups[ApplicationGroup].groups[orgName].values[BootstrapHelper.KEY_ANCHOR_PEERS].value=toValue(anchorPeers)
        config_group.groups[ApplicationGroup].groups[orgName].values[BootstrapHelper.KEY_ANCHOR_PEERS].mod_policy = BootstrapHelper.KEY_POLICY_ADMINS
    return config_group

def set_default_msp_config_for_orgs(directory, channel, group_name, orgs):
    for org in orgs:
        channel.groups[group_name].groups[org.name].values[BootstrapHelper.KEY_MSP_INFO].value = BootstrapHelper.toValue(
            get_msp_config(org=org, directory=directory))
        channel.groups[group_name].groups[org.name].values[BootstrapHelper.KEY_MSP_INFO].mod_policy=BootstrapHelper.KEY_POLICY_ADMINS


def set_default_policies_for_orgs(channel, orgs, group_name, version=0, policy_version=0):
    for org in orgs:
        groupName = group_name
        channel.groups[groupName].groups[org.name].version=version
        channel.groups[groupName].groups[org.name].mod_policy = BootstrapHelper.KEY_POLICY_ADMINS
        mspPrincipalForMemberRole = org.getMspPrincipalAsRole(mspRoleTypeAsString='MEMBER')
        signedBy = AuthDSLHelper.SignedBy(0)

        memberSignaturePolicyEnvelope = AuthDSLHelper.Envelope(signaturePolicy=AuthDSLHelper.NOutOf(1, [signedBy]), identities=[mspPrincipalForMemberRole])
        memberPolicy = common_dot_policies_pb2.Policy(
            type=common_dot_policies_pb2.Policy.PolicyType.Value("SIGNATURE"),
            value=memberSignaturePolicyEnvelope.SerializeToString())
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_READERS].version=policy_version
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_READERS].policy.CopyFrom(memberPolicy)
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_WRITERS].version=policy_version
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_WRITERS].policy.CopyFrom(memberPolicy)

        mspPrincipalForAdminRole = org.getMspPrincipalAsRole(mspRoleTypeAsString='ADMIN')
        adminSignaturePolicyEnvelope = AuthDSLHelper.Envelope(signaturePolicy=AuthDSLHelper.NOutOf(1, [signedBy]), identities=[mspPrincipalForAdminRole])
        adminPolicy = common_dot_policies_pb2.Policy(
            type=common_dot_policies_pb2.Policy.PolicyType.Value("SIGNATURE"),
            value=adminSignaturePolicyEnvelope.SerializeToString())
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_ADMINS].version=policy_version
        channel.groups[groupName].groups[org.name].policies[BootstrapHelper.KEY_POLICY_ADMINS].policy.CopyFrom(adminPolicy)

        for pKey, pVal in channel.groups[groupName].groups[org.name].policies.iteritems():
            pVal.mod_policy = BootstrapHelper.KEY_POLICY_ADMINS


def create_envelope_for_msg(directory, nodeAdminTuple, chainId, msg, typeAsString):
    payloadChainHeader = make_chain_header(type=common_dot_common_pb2.HeaderType.Value(typeAsString), channel_id=chainId)

    # Now the SignatureHeader
    org = directory.getOrganization(nodeAdminTuple.organization)
    user = directory.getUser(nodeAdminTuple.user)
    cert = directory.findCertForNodeAdminTuple(nodeAdminTuple)
    serializedIdentity = identities_pb2.SerializedIdentity(mspid=org.name, id_bytes=crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    serializedCreatorCertChain = serializedIdentity.SerializeToString()
    nonce = None
    payloadSignatureHeader = common_dot_common_pb2.SignatureHeader(
        creator=serializedCreatorCertChain,
        nonce=BootstrapHelper.getNonce(),
    )

    payloadHeader = common_dot_common_pb2.Header(
        channel_header=payloadChainHeader.SerializeToString(),
        signature_header=payloadSignatureHeader.SerializeToString(),
    )
    payload = common_dot_common_pb2.Payload(header=payloadHeader, data=msg.SerializeToString())
    payloadBytes = payload.SerializeToString()
    envelope = common_dot_common_pb2.Envelope(payload=payloadBytes, signature=user.sign(payloadBytes))
    return envelope

    return configEnvelope


def createNewConfigUpdateEnvelope(channelConfig, chainId, readset_version=0):
    read_set = common_dot_configtx_pb2.ConfigGroup()
    read_set.values[BootstrapHelper.KEY_CONSORTIUM].version=readset_version
    read_set.values[BootstrapHelper.KEY_CONSORTIUM].value=channelConfig.values[BootstrapHelper.KEY_CONSORTIUM].value
    read_set.groups[ApplicationGroup].version=readset_version
    for key, _ in channelConfig.groups['Application'].groups.iteritems():
        read_set.groups[ApplicationGroup].groups[key]
    configUpdate = common_dot_configtx_pb2.ConfigUpdate(channel_id=chainId,
                                                        read_set=read_set,
                                                        write_set=channelConfig)
    configUpdateEnvelope = common_dot_configtx_pb2.ConfigUpdateEnvelope(config_update=configUpdate.SerializeToString(), signatures =[])
    return configUpdateEnvelope


def merge_config_groups(configGroupTarget, configGroupSource, allow_value_overwrite=False):
    for k, v in configGroupSource.groups.iteritems():
        if k in configGroupTarget.groups.keys():
            merge_config_groups(configGroupTarget.groups[k], configGroupSource.groups[k], allow_value_overwrite=allow_value_overwrite)
        else:
            configGroupTarget.groups[k].MergeFrom(v)
    for k, v in configGroupSource.policies.iteritems():
        if k in configGroupTarget.policies.keys():
            merge_config_groups(configGroupTarget.policies[k], configGroupSource.policies[k], allow_value_overwrite=allow_value_overwrite)
        else:
            configGroupTarget.policies[k].MergeFrom(v)
    for k, v in configGroupSource.values.iteritems():
        if not allow_value_overwrite:
            assert not k in configGroupTarget.values.keys(), "Value already exists in target config group: {0}".format(k)
        configGroupTarget.values[k].CopyFrom(v)




class PathType(Enum):
    'Denotes whether Path relative to Local filesystem or Containers volume reference.'
    Local = 1
    Container = 2


def get_msp_config(org, directory):
    # CA certificates can't be admins of an MSP
    # adminCerts = [org.getCertAsPEM()]
    adminCerts = []
    # Find the mspAdmin Tuple for org and add to admincerts folder
    for pnt, cert in directory.find_config_admins_for_org(org=org):
        adminCerts.append(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    cacerts = [org.getCertAsPEM()]
    tls_root_certs = [org.getCertAsPEM()]
    # Currently only 1 component, CN=<orgName>
    # name = self.getSelfSignedCert().get_subject().getComponents()[0][1]
    fabricMSPConfig = msp_config_pb2.FabricMSPConfig(admins=adminCerts, root_certs=cacerts, name=org.name, tls_root_certs=tls_root_certs)
    mspConfig = msp_config_pb2.MSPConfig(config=fabricMSPConfig.SerializeToString(), type=0)
    return mspConfig


class LocalMspConfig(Enum):
    admincerts = 1
    cacerts = 2
    intermediatecacerts = 3
    signcerts = 4
    keystore = 5
    tlscacerts = 6
    tlsintermediatecacerts = 7

class CallbackHelper:


    def __init__(self, discriminator, volumeRootPathInContainer = "/var/hyperledger/bddtests", volumeRootPathLocal = "/var/hyperledger/bddtests"):
        self.volumeRootPathInContainer = volumeRootPathInContainer
        self.volumeRootPathLocal = volumeRootPathLocal
        self.discriminator = discriminator

    def get_service_list(self, composition):
        return [serviceName for serviceName in composition.getServiceNames() if self.discriminator in serviceName]

    def getVolumePath(self, project_name, pathType=PathType.Local):
        # assert pathType in PathType, "Expected pathType of {0}".format(PathType)
        basePath = self.volumeRootPathLocal
        if pathType == PathType.Container:
            basePath = self.volumeRootPathInContainer
        return "{0}/volumes/{1}/{2}".format(basePath, self.discriminator, project_name)

    def getLocalMspConfigPath(self, project_name, compose_service, pathType=PathType.Local):
        return "{0}/{1}/localMspConfig".format(self.getVolumePath(project_name=project_name, pathType=pathType), compose_service)

    def getLocalTLSConfigPath(self, project_name, compose_service, pathType=PathType.Local):
        return os.path.join(self.getVolumePath(project_name=project_name, pathType=pathType), compose_service, "tls_config")

    def _getPathAndUserInfo(self, directory , project_name, compose_service, nat_discriminator="Signer", pathType=PathType.Local):
        matchingNATs = [nat for nat in directory.getNamedCtxTuples() if ((compose_service in nat.user) and (nat_discriminator in nat.user) and ((compose_service in nat.nodeName)))]
        assert len(matchingNATs)==1, "Unexpected number of matching NodeAdminTuples: {0}".format(matchingNATs)
        localMspConfigPath = self.getLocalMspConfigPath(project_name=project_name, compose_service=compose_service,pathType=pathType)
        return (localMspConfigPath, matchingNATs[0])

    def getLocalMspConfigPrivateKeyPath(self, directory , project_name, compose_service, pathType=PathType.Local):
        (localMspConfigPath, nodeAdminTuple) = self._getPathAndUserInfo(directory=directory, project_name=project_name, compose_service=compose_service, pathType=pathType)
        return "{0}/keystore/{1}.pem".format(localMspConfigPath, nodeAdminTuple.user)

    def getLocalMspConfigPublicCertPath(self, directory , project_name, compose_service, pathType=PathType.Local):
        (localMspConfigPath, nodeAdminTuple) = self._getPathAndUserInfo(directory=directory, project_name=project_name, compose_service=compose_service, pathType=pathType)
        return "{0}/signcerts/{1}.pem".format(localMspConfigPath, nodeAdminTuple.user)

    def getTLSKeyPaths(self, pnt , project_name, compose_service, pathType=PathType.Local):
        localTLSConfigPath = self.getLocalTLSConfigPath(project_name=project_name, compose_service=compose_service, pathType=pathType)
        certPath = os.path.join(localTLSConfigPath,
                                "{0}-{1}-{2}-tls.crt".format(pnt.user, pnt.nodeName, pnt.organization))
        keyPath = os.path.join(localTLSConfigPath,
                               "{0}-{1}-{2}-tls.key".format(pnt.user, pnt.nodeName, pnt.organization))
        return (keyPath, certPath)


    def glob_recursive(self, root_dir='.', pattern='*'):
        matches = []
        import glob
        for root, dirnames, filenames in os.walk(root_dir):
            for filename in glob.fnmatch.filter(filenames, pattern):
                matches.append(os.path.join(root, filename))
        return matches

    def getFilestorePath(self, project_name, compose_service, pathType=PathType.Local):
        assert pathType in PathType, "Expected pathType of {0}".format(PathType)
        basePath = self.volumeRootPathLocal
        if pathType == PathType.Container:
            basePath = self.volumeRootPathInContainer
        return "{0}/volumes/{1}/{2}/{3}/filestore".format(basePath, self.discriminator, project_name, compose_service)


    def _copy_filestore(self, src_path, dest_path):
        assert os.path.exists(src_path), "Filestore source path not found: {0}".format(src_path)
        cli_call(['sudo','cp', '-r', src_path, dest_path])

    def get_snapshot_path(self, project_name, compose_service, snapshot, pathType=PathType.Local):
        "Returns the snapshot path calculated per the supplied snapshot name."
        file_store_path = self.getFilestorePath(project_name=project_name, compose_service=compose_service, pathType=pathType)
        return "{0}-{1}".format(file_store_path, snapshot)

    def snapshot_filestore(self, project_name, compose_service, snapshot, pathType=PathType.Local):
        file_store_path = self.getFilestorePath(project_name=project_name, compose_service=compose_service, pathType=pathType)
        assert os.path.exists(file_store_path), "Filestore path not found for service {0}: {1}".format(compose_service, file_store_path)
        destination_path = "{0}-{1}".format(file_store_path, snapshot)
        self._copy_filestore(src_path=file_store_path, dest_path=destination_path)
        return destination_path

    def restore_filestore_snapshot(self, project_name, compose_service, snapshot, pathType=PathType.Local):
        '''Restores the supplied snapshot WARNING: Will attempt to delete the existing filestore folder first!!!!'''
        file_store_path = self.getFilestorePath(project_name=project_name, compose_service=compose_service, pathType=pathType)
        # First remove the existing filestore folder
        cli_call(['sudo','rm','-rf', file_store_path])
        assert not os.path.exists(file_store_path), "Filestore path already exists for service {0}: {1}".format(compose_service, file_store_path)
        src_path = "{0}-{1}".format(file_store_path, snapshot)
        self._copy_filestore(src_path=src_path, dest_path=file_store_path)

    def getLocalMspConfigRootCertPath(self, directory , project_name, compose_service, pathType=PathType.Local):
        (localMspConfigPath, nodeAdminTuple) = self._getPathAndUserInfo(directory=directory, project_name=project_name, compose_service=compose_service, pathType=pathType)
        return "{0}/cacerts/{1}.pem".format(localMspConfigPath, nodeAdminTuple.organization)

    def _createCryptoMaterial(self,directory , project_name, compose_service, network):
        self._writeMspFiles(directory , project_name=project_name, compose_service=compose_service, network=network)
        self._writeTLSFiles(directory , project_name=project_name, compose_service=compose_service, network=network)

    def _createFilestore(self, project_name, compose_service):
        local_filestore_path = self.getFilestorePath(project_name=project_name, compose_service=compose_service)
        os.makedirs("{0}".format(local_filestore_path))


    def _writeMspFiles(self, directory , project_name, compose_service, network):
        localMspConfigPath = self.getLocalMspConfigPath(project_name, compose_service)
        os.makedirs("{0}/{1}".format(localMspConfigPath, "signcerts"))
        os.makedirs("{0}/{1}".format(localMspConfigPath, "admincerts"))
        os.makedirs("{0}/{1}".format(localMspConfigPath, "cacerts"))
        #TODO: Consider how to accomodate intermediate CAs
        os.makedirs("{0}/{1}".format(localMspConfigPath, "intermediatecacerts"))
        os.makedirs("{0}/{1}".format(localMspConfigPath, "keystore"))
        os.makedirs("{0}/{1}".format(localMspConfigPath, "tlscacerts"))
        #TODO: Consider how to accomodate intermediate CAs
        os.makedirs("{0}/{1}".format(localMspConfigPath, "tlsintermediatecacerts"))

        # Find the peer signer Tuple for this peer and add to signcerts folder
        for pnt, cert in [(peerNodeTuple, cert) for peerNodeTuple, cert in directory.ordererAdminTuples.items() if
                          compose_service in peerNodeTuple.user and "signer" in peerNodeTuple.user.lower()]:
            # Put the PEM file in the signcerts folder
            with open("{0}/signcerts/{1}.pem".format(localMspConfigPath, pnt.user), "w") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
            # Put the associated private key into the keystore folder
            user = directory.getUser(pnt.user, shouldCreate=False)
            with open("{0}/keystore/{1}.pem".format(localMspConfigPath, pnt.user), "w") as f:
                f.write(user.ecdsaSigningKey.to_pem())

            #Now put the signing Orgs cert in the cacerts folder
            org_cert_as_pem =  directory.getOrganization(pnt.organization).getCertAsPEM()
            with open("{0}/cacerts/{1}.pem".format(localMspConfigPath, pnt.organization), "w") as f:
                f.write(org_cert_as_pem)
            with open("{0}/tlscacerts/{1}.pem".format(localMspConfigPath, pnt.organization), "w") as f:
                f.write(org_cert_as_pem)

        # Find the peer admin Tuple for this peer and add to admincerts folder
        for pnt, cert in [(peerNodeTuple, cert) for peerNodeTuple, cert in directory.ordererAdminTuples.items() if
                          compose_service in peerNodeTuple.user and "admin" in peerNodeTuple.user.lower()]:
            # Put the PEM file in the signcerts folder
            with open("{0}/admincerts/{1}.pem".format(localMspConfigPath, pnt.user), "w") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    def _writeTLSFiles(self, directory , project_name, compose_service, network):
        localTLSConfigPath = self.getLocalTLSConfigPath(project_name, compose_service)
        os.makedirs(localTLSConfigPath)
        # Find the peer signer Tuple for this peer and add to signcerts folder
        for pnt, cert in [(peerNodeTuple, cert) for peerNodeTuple, cert in directory.ordererAdminTuples.items() if
                          compose_service in peerNodeTuple.user and "signer" in peerNodeTuple.user.lower()]:
            user = directory.getUser(userName=pnt.user)
            # Add the subjectAlternativeName if the current entity is a signer, and the nodeName contains peer or orderer
            extensions = directory._get_cert_extensions_ip_sans(user.name, pnt.nodeName)
            userTLSCert = directory.getOrganization(pnt.organization).createCertificate(user.createTLSCertRequest(pnt.nodeName), extensions=extensions)
            (keyPath, certPath) = self.getTLSKeyPaths(pnt=pnt, project_name=project_name, compose_service=compose_service, pathType=PathType.Local)
            with open(keyPath, 'w') as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, user.rsaSigningKey))
            with open(certPath, 'w') as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, userTLSCert))

    def _getMspId(self, compose_service, directory):
        matchingNATs = [nat for nat in directory.getNamedCtxTuples() if ((compose_service in nat.user) and ("Signer" in nat.user) and ((compose_service in nat.nodeName)))]
        assert len(matchingNATs)==1, "Unexpected number of matching NodeAdminTuples: {0}".format(matchingNATs)
        return matchingNATs[0].organization

class OrdererGensisBlockCompositionCallback(compose.CompositionCallback, CallbackHelper):
    'Responsible for setting the GensisBlock for the Orderer nodes upon composition'

    DISCRIMINATOR = "orderer"

    def __init__(self, context, genesisFileName="genesis_file"):
        CallbackHelper.__init__(self, discriminator="orderer")
        self.context = context
        self.genesisFileName = genesisFileName
        compose.Composition.RegisterCallbackInContext(context, self)
        # Now initialize the Kafka composition callbacks
        KafkaCompositionCallback(context=context)
        ZookeeperCompositionCallback(context=context)

    def getGenesisFilePath(self, project_name, pathType=PathType.Local):
        return "{0}/{1}".format(self.getVolumePath(project_name=project_name, pathType=pathType), self.genesisFileName)

    @classmethod
    def get_orderer_service_list(cls, composition):
        return [serviceName for serviceName in composition.getServiceNames() if "orderer" in serviceName]

    def write_genesis_file(self, composition, genesis_block):
        print("Will copy gensisiBlock over at this point ")
        with open(self.getGenesisFilePath(composition.projectName), "wb") as f:
            f.write(genesis_block.SerializeToString())

    def composing(self, composition, context):
        print("Will copy gensisiBlock over at this point ")
        os.makedirs(self.getVolumePath(composition.projectName))
        directory = getDirectory(context)

        for ordererService in OrdererGensisBlockCompositionCallback.get_orderer_service_list(composition):
            self._createCryptoMaterial(directory=directory,
                                       compose_service=ordererService,
                                       project_name=composition.projectName,
                                       network=Network.Orderer)
            self._createFilestore(compose_service=ordererService,
                                  project_name=composition.projectName)

    def decomposing(self, composition, context):
        'Will remove the orderer volume path folder for the context'
        shutil.rmtree(self.getVolumePath(composition.projectName))

    def getEnv(self, composition, context, env):
        directory = getDirectory(context)
        env["ORDERER_GENERAL_GENESISMETHOD"] = "file"
        env["ORDERER_GENERAL_GENESISFILE"] = self.getGenesisFilePath(composition.projectName, pathType=PathType.Container)
        for ordererService in OrdererGensisBlockCompositionCallback.get_orderer_service_list(composition):
            localMspConfigPath = self.getLocalMspConfigPath(composition.projectName, ordererService, pathType=PathType.Container)
            env["{0}_ORDERER_GENERAL_LOCALMSPDIR".format(ordererService.upper())] = localMspConfigPath
            env["{0}_ORDERER_GENERAL_LOCALMSPID".format(ordererService.upper())] = self._getMspId(compose_service=ordererService, directory=directory)
            # TLS Settings
            (_, pnt) = self._getPathAndUserInfo(directory=directory, project_name=composition.projectName, compose_service=ordererService, pathType=PathType.Container)
            (keyPath, certPath) = self.getTLSKeyPaths(pnt=pnt, project_name=composition.projectName, compose_service=ordererService, pathType=PathType.Container)
            env["{0}_ORDERER_GENERAL_TLS_CERTIFICATE".format(ordererService.upper())] = certPath
            env["{0}_ORDERER_GENERAL_TLS_PRIVATEKEY".format(ordererService.upper())] = keyPath

            env["{0}_ORDERER_GENERAL_CLUSTER_CLIENTPRIVATEKEY".format(ordererService.upper())] = keyPath
            env["{0}_ORDERER_GENERAL_CLUSTER_CLIENTCERTIFICATE".format(ordererService.upper())] = certPath

            env["{0}_ORDERER_GENERAL_TLS_ROOTCAS".format(ordererService.upper())] = "[{0}]".format(self.getLocalMspConfigRootCertPath(
                directory=directory, project_name=composition.projectName, compose_service=ordererService, pathType=PathType.Container))
            # The Filestore settings
            container_filestore_path = self.getFilestorePath(project_name=composition.projectName, compose_service=ordererService, pathType=PathType.Container)
            env["{0}_ORDERER_FILELEDGER_LOCATION".format(ordererService.upper())] = container_filestore_path

            # Now the Raft settings
            env["{0}_ORDERER_CONSENSUS_WALDIR".format(ordererService.upper())] = os.path.join(container_filestore_path, "etcdraft", "waldir")
            env["{0}_ORDERER_CONSENSUS_SNAPDIR".format(ordererService.upper())] = os.path.join(container_filestore_path, "etcdraft", "snapdir")

            # Now the orderer image if it is set
            version_for_orderer = composition.get_version_for_service(ordererService)
            if version_for_orderer:
                env["{0}_VERSION_EXTENSION".format(ordererService.upper())] = ":{0}".format(version_for_orderer)


class CouchDBCompositionCallback(compose.CompositionCallback, CallbackHelper):
    'Responsible for setting up Kafka nodes upon composition'


    DISCRIMINATOR = "couchdb"

    def __init__(self, context):
        CallbackHelper.__init__(self, discriminator="couchdb")
        self.context = context
        compose.Composition.RegisterCallbackInContext(context, self)

    def get_couchdb_service_list(self, composition):
        return [serviceName for serviceName in composition.getServiceNames() if "couchdb" in serviceName]

    def composing(self, composition, context):
        'Will create the filestore folder for each node'
        directory = getDirectory(context)
        for couchdb_service in self.get_couchdb_service_list(composition):
            self._createFilestore(compose_service=couchdb_service,
                                  project_name=composition.projectName)

    def decomposing(self, composition, context):
        'Will remove the orderer volume path folder for the context'
        shutil.rmtree(self.getVolumePath(composition.projectName))

    def getEnv(self, composition, context, env):
        directory = getDirectory(context)
        for couchdb_service in self.get_couchdb_service_list(composition):
            # The Filestore settings
            container_filestore_path = self.getFilestorePath(project_name=composition.projectName, compose_service=couchdb_service, pathType=PathType.Local)
            env["{0}_HOST_DATA_DIR".format(couchdb_service.upper())] = container_filestore_path

            # Now the versions
            version_for_couchdb = composition.get_version_for_service(couchdb_service)
            env["{0}_VERSION_EXTENSION".format(couchdb_service.upper())] = ":{0}".format(version_for_couchdb)


class PeerCompositionCallback(compose.CompositionCallback, CallbackHelper):
    'Responsible for setting up Peer nodes upon composition'

    DISCRIMINATOR = "peer"

    def __init__(self, context):
        CallbackHelper.__init__(self, discriminator="peer")
        self.context = context
        compose.Composition.RegisterCallbackInContext(context, self)
        # Now initialize the CouchDB composition callbacks
        CouchDBCompositionCallback(context=context)


    def get_couchdb_service_for_peer(self, compose_service, composition_config_as_yaml):
        'Returns the couchdb service for this peer or None if none found.'
        assert PeerCompositionCallback.DISCRIMINATOR in compose_service, "Expected a peer compose service, received: {0}".format(compose_service)
        couchdb_services = [c for c in composition_config_as_yaml['services'][compose_service]['depends_on'] if c.startswith(CouchDBCompositionCallback.DISCRIMINATOR)]
        assert len(couchdb_services) <= 1, "Expected either exactly one or no dependent services starting with {0} for peer {1}".format(CouchDBCompositionCallback.DISCRIMINATOR, compose_service)
        return couchdb_services[0] if len(couchdb_services)==1 else None


    def getPeerList(self, composition):
        return [serviceName for serviceName in composition.getServiceNames() if "peer" in serviceName]

    def composing(self, composition, context):
        'Will copy local MSP info over at this point for each peer node'

        directory = getDirectory(context)

        for peerService in self.getPeerList(composition):
            self._createCryptoMaterial(directory=directory,
                                       compose_service=peerService,
                                       project_name=composition.projectName,
                                       network=Network.Peer)
            self._createFilestore(compose_service=peerService,
                                  project_name=composition.projectName)


    def decomposing(self, composition, context):
        'Will remove the orderer volume path folder for the context'
        shutil.rmtree(self.getVolumePath(composition.projectName))

    def getEnv(self, composition, context, env):
        directory = getDirectory(context)
        # First figure out which organization provided the signer cert for this
        for peerService in self.getPeerList(composition):
            localMspConfigPath = self.getLocalMspConfigPath(composition.projectName, peerService, pathType=PathType.Container)
            env["{0}_CORE_PEER_MSPCONFIGPATH".format(peerService.upper())] = localMspConfigPath
            env["{0}_CORE_PEER_LOCALMSPID".format(peerService.upper())] = self._getMspId(compose_service=peerService, directory=directory)
            # TLS Settings
            # env["{0}_CORE_PEER_TLS_ENABLED".format(peerService.upper())] = self._getMspId(compose_service=peerService, directory=directory)
            (_, pnt) = self._getPathAndUserInfo(directory=directory, project_name=composition.projectName, compose_service=peerService, pathType=PathType.Container)
            (keyPath, certPath) = self.getTLSKeyPaths(pnt=pnt, project_name=composition.projectName, compose_service=peerService, pathType=PathType.Container)
            env["{0}_CORE_PEER_TLS_CERT_FILE".format(peerService.upper())] = certPath
            env["{0}_CORE_PEER_TLS_KEY_FILE".format(peerService.upper())] = keyPath
            env["{0}_CORE_PEER_TLS_ROOTCERT_FILE".format(peerService.upper())] = self.getLocalMspConfigRootCertPath(
                directory=directory, project_name=composition.projectName, compose_service=peerService, pathType=PathType.Container)
            env["{0}_CORE_PEER_TLS_SERVERHOSTOVERRIDE".format(peerService.upper())] = peerService
            # The Filestore settings
            container_filestore_path = self.getFilestorePath(project_name=composition.projectName, compose_service=peerService, pathType=PathType.Container)
            env["{0}_CORE_PEER_FILESYSTEMPATH".format(peerService.upper())] = container_filestore_path

            # Now the peer image if it is set
            version_for_peer = composition.get_version_for_service(peerService)
            if version_for_peer:
                env["{0}_VERSION_EXTENSION".format(peerService.upper())] = ":{0}".format(version_for_peer)


class KafkaCompositionCallback(compose.CompositionCallback, CallbackHelper):
    'Responsible for setting up Kafka nodes upon composition'

    DISCRIMINATOR = "kafka"

    REPLICA_HIGH_WATERMARK_CHECKPOINT_INTERVAL_MS = 6000

    def __init__(self, context):
        CallbackHelper.__init__(self, discriminator="kafka")
        self.context = context
        compose.Composition.RegisterCallbackInContext(context, self)

    @classmethod
    def get_kafka_service_list(cls, composition):
        return [serviceName for serviceName in composition.getServiceNames() if "kafka" in serviceName]

    def composing(self, composition, context):
        'Will create the filestore folder for each kafka node'
        directory = getDirectory(context)

        for kafka_service in KafkaCompositionCallback.get_kafka_service_list(composition):
            self._createFilestore(compose_service=kafka_service,
                                  project_name=composition.projectName)


    def decomposing(self, composition, context):
        'Will remove the orderer volume path folder for the context'
        shutil.rmtree(self.getVolumePath(composition.projectName))

    def getEnv(self, composition, context, env):
        directory = getDirectory(context)
        for kafka_service in KafkaCompositionCallback.get_kafka_service_list(composition):
            # The Filestore settings
            container_filestore_path = self.getFilestorePath(project_name=composition.projectName, compose_service=kafka_service, pathType=PathType.Container)
            env["{0}_KAFKA_LOG_DIRS".format(kafka_service.upper())] = container_filestore_path

            # Now the Kafka versions
            version_for_kafka = composition.get_version_for_service(kafka_service)
            env["{0}_VERSION_EXTENSION".format(kafka_service.upper())] = ":{0}".format(version_for_kafka)


class ZookeeperCompositionCallback(compose.CompositionCallback, CallbackHelper):
    'Responsible for setting up Kafka nodes upon composition'

    def __init__(self, context):
        CallbackHelper.__init__(self, discriminator="zookeeper")
        self.context = context
        compose.Composition.RegisterCallbackInContext(context, self)

    def get_zk_service_list(self, composition):
        return [serviceName for serviceName in composition.getServiceNames() if "zookeeper" in serviceName]

    def composing(self, composition, context):
        'Will create the filestore folder for each node'
        directory = getDirectory(context)
        for zk_service in self.get_zk_service_list(composition):
            self._createFilestore(compose_service=zk_service,
                                  project_name=composition.projectName)

    def decomposing(self, composition, context):
        'Will remove the orderer volume path folder for the context'
        shutil.rmtree(self.getVolumePath(composition.projectName))

    def getEnv(self, composition, context, env):
        directory = getDirectory(context)
        for zk_service in self.get_zk_service_list(composition):
            # The Filestore settings
            container_filestore_path = self.getFilestorePath(project_name=composition.projectName, compose_service=zk_service, pathType=PathType.Container)
            env["{0}_ZOO_DATA_DIR".format(zk_service.upper())] = container_filestore_path

            # Now the versions
            version_for_zk = composition.get_version_for_service(zk_service)
            env["{0}_VERSION_EXTENSION".format(zk_service.upper())] = ":{0}".format(version_for_zk)



def getDefaultConsortiumGroup(consortiums_mod_policy):
    default_config_group = common_dot_configtx_pb2.ConfigGroup()
    consortiums_config_group = default_config_group.groups[ConsortiumsGroup]
    consortiums_config_group.mod_policy=consortiums_mod_policy
    acceptAllPolicy = common_dot_policies_pb2.Policy(type=common_dot_policies_pb2.Policy.PolicyType.Value("SIGNATURE"),
                                                     value=AuthDSLHelper.Envelope(signaturePolicy=AuthDSLHelper.NOutOf(0, []), identities=[]).SerializeToString())
    consortiums_config_group.policies[BootstrapHelper.KEY_POLICY_ADMINS].policy.CopyFrom(acceptAllPolicy)
    for pKey, pVal in consortiums_config_group.policies.iteritems():
        pVal.mod_policy = consortiums_mod_policy


    return default_config_group


def create_config_update_envelope(config_update):
    return  common_dot_configtx_pb2.ConfigUpdateEnvelope(config_update=config_update.SerializeToString(), signatures =[])

def create_orderer_consortium_config_update(orderer_system_chain_id, orderer_channel_group, config_groups):
    'Creates the orderer config update'
    # First determine read set
    read_set = common_dot_configtx_pb2.ConfigGroup()
    read_set.groups[ConsortiumsGroup].CopyFrom(orderer_channel_group.groups[ConsortiumsGroup])

    write_set = common_dot_configtx_pb2.ConfigGroup()
    write_set.groups[ConsortiumsGroup].CopyFrom(orderer_channel_group.groups[ConsortiumsGroup])
    write_set.groups[ConsortiumsGroup].version += 1
    for config_group in config_groups:
        merge_config_groups(write_set, config_group)
    config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=orderer_system_chain_id,
                                                        read_set=read_set,
                                                        write_set=write_set)
    # configUpdateEnvelope = common_dot_configtx_pb2.ConfigUpdateEnvelope(config_update=configUpdate.SerializeToString(), signatures =[])
    return config_update

def create_orderer_consensus_state_config_update(orderer_system_chain_id, orderer_channel_group, consensusState):
    'Creates the orderer config update for modifying the consensus state (NORMAL|MAINTENANCE)'
    # First determine read set
    read_set = common_dot_configtx_pb2.ConfigGroup()
    # do NOT believe I need to increment the /Channel version, so simply copying from provided.
    read_set.CopyFrom(orderer_channel_group)
    curr_consensustype_config_value = orderer_channel_group.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE]

    write_set = common_dot_configtx_pb2.ConfigGroup()
    write_set.CopyFrom(read_set)
    # Have to clear the values
    write_set.values.clear()
    # Can only update 1 group, so pop Consortiums if defined
    write_set.groups.pop(ConsortiumsGroup, None)
    # Remove any groups under /Channel/Orderer
    write_set.groups[OrdererGroup].groups.clear()

    new_consensustype = orderer_dot_configuration_pb2.ConsensusType()
    new_consensustype.ParseFromString(curr_consensustype_config_value.value)
    # Change to the desired state
    new_consensustype.state = orderer_dot_configuration_pb2.ConsensusType.State.Value(consensusState)
    # Can only contain the one value
    write_set.groups[OrdererGroup].values.clear()
    write_set.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE].CopyFrom(curr_consensustype_config_value)
    write_set.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE].value = new_consensustype.SerializeToString()
    write_set.groups[OrdererGroup].values[BootstrapHelper.KEY_CONSENSUS_TYPE].version += 1

    config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=orderer_system_chain_id,
                                                         read_set=read_set,
                                                         write_set=write_set)
    # configUpdateEnvelope = common_dot_configtx_pb2.ConfigUpdateEnvelope(config_update=configUpdate.SerializeToString(), signatures =[])
    return config_update


def create_channel_config_update(system_channel_version, channel_id, consortium_config_group):
    read_set = common_dot_configtx_pb2.ConfigGroup()
    read_set.version = system_channel_version
    read_set.values[BootstrapHelper.KEY_CONSORTIUM].value=toValue(common_dot_configuration_pb2.Consortium(name=consortium_config_group.groups[ConsortiumsGroup].groups.keys()[0]))

    # Copying all of the consortium orgs into the ApplicationGroup
    read_set.groups[ApplicationGroup].CopyFrom(consortium_config_group.groups[ConsortiumsGroup].groups.values()[0])
    read_set.groups[ApplicationGroup].values.clear()
    read_set.groups[ApplicationGroup].policies.clear()
    read_set.groups[ApplicationGroup].mod_policy=""
    for k, v in read_set.groups[ApplicationGroup].groups.iteritems():
        v.values.clear()
        v.policies.clear()
        v.mod_policy=""

    # Now the write_set
    write_set = common_dot_configtx_pb2.ConfigGroup()
    write_set.CopyFrom(read_set)
    write_set.groups[ApplicationGroup].version += 1
    # For now, setting same policies for each 'Non-Org' group
    typeImplicitMeta = common_dot_policies_pb2.Policy.PolicyType.Value("IMPLICIT_META")
    Policy = common_dot_policies_pb2.Policy
    IMP = common_dot_policies_pb2.ImplicitMetaPolicy
    ruleAny = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("ANY")
    ruleMajority = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("MAJORITY")
    write_set.groups[ApplicationGroup].policies[BootstrapHelper.KEY_POLICY_READERS].policy.CopyFrom(
        Policy(type=typeImplicitMeta, value=IMP(
            rule=ruleAny, sub_policy=BootstrapHelper.KEY_POLICY_READERS).SerializeToString()))
    write_set.groups[ApplicationGroup].policies[BootstrapHelper.KEY_POLICY_WRITERS].policy.CopyFrom(
        Policy(type=typeImplicitMeta, value=IMP(
            rule=ruleAny, sub_policy=BootstrapHelper.KEY_POLICY_WRITERS).SerializeToString()))
    write_set.groups[ApplicationGroup].policies[BootstrapHelper.KEY_POLICY_ADMINS].policy.CopyFrom(
        Policy(type=typeImplicitMeta, value=IMP(
            rule=ruleMajority, sub_policy=BootstrapHelper.KEY_POLICY_ADMINS).SerializeToString()))
    write_set.groups[ApplicationGroup].mod_policy = "Admins"
    for k, v in write_set.groups[ApplicationGroup].policies.iteritems():
        v.mod_policy=BootstrapHelper.KEY_POLICY_ADMINS
    config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=channel_id,
                                                         read_set=read_set,
                                                         write_set=write_set)
    return config_update

def get_group_paths_from_config_group(config_group, paths, current_path = ""):
    if len(config_group.groups)==0:
        paths.append(current_path)
    else:
        for group_name, group in config_group.groups.iteritems():
            get_group_paths_from_config_group(config_group=group, current_path="{0}/{1}".format(current_path, group_name), paths=paths)
    return paths


def get_group_from_config_path(config_group, config_path):
    from os import path
    current_config_group = config_group
    for group_id in [g.strip("/") for g in path.split(config_path)]:
        current_config_group = current_config_group.groups[group_id]
    return current_config_group

def create_existing_channel_config_update(system_channel_version, channel_id, input_config_update, config_groups):
    # First make a copy of the input config update msg to manipulate
    read_set = common_dot_configtx_pb2.ConfigGroup()
    read_set.version = system_channel_version
    read_set.CopyFrom(input_config_update)

    # Now the write_set
    write_set = common_dot_configtx_pb2.ConfigGroup()
    write_set.CopyFrom(read_set)

    # Merge all of the supplied config_groups
    for config_group in config_groups:
        merge_config_groups(write_set, config_group)

    # Will build a unique list of group paths from the supplied config_groups
    group_paths = list(set([p for sublist in [get_group_paths_from_config_group(cg, paths=[]) for cg in config_groups] for p in sublist]))

    # Now increment the version for each path.
    # TODO: This logic will only work for the case of insertions
    for group in [get_group_from_config_path(write_set, g) for g in group_paths]:
        group.version += 1

    # For now, setting same policies for each 'Non-Org' group
    config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=channel_id,
                                                         read_set=read_set,
                                                         write_set=write_set)
    return config_update

def update_config_group_version_info(input_config_update, proposed_config_group):
    for k,v in proposed_config_group.groups.iteritems():
        if k in input_config_update.groups.keys():
            # Make sure all keys of the current group match those of the proposed, if not either added or deleted.
            if not set(proposed_config_group.groups[k].groups.keys()) == set(input_config_update.groups[k].groups.keys()):
                proposed_config_group.groups[k].version +=1
            # Now recurse
            update_config_group_version_info(input_config_update.groups[k], proposed_config_group.groups[k])

# def create_existing_channel_config_update2(system_channel_version, channel_id, input_config_update, config_group):
#     # First make a copy of the input config update msg to manipulate
#     read_set = common_dot_configtx_pb2.ConfigGroup()
#     read_set.version = system_channel_version
#     read_set.CopyFrom(config_group)
#
#     # Now the write_set
#     write_set = common_dot_configtx_pb2.ConfigGroup()
#     write_set.CopyFrom(read_set)
#     mergeConfigGroups(write_set, config_groups[0])
#     write_set.groups['Application'].groups['peerOrg0'].version +=1
#
#     # write_set.groups[ApplicationGroup].version += 1
#     # For now, setting same policies for each 'Non-Org' group
#     config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=channel_id,
#                                                          read_set=read_set,
#                                                          write_set=write_set)
#     return config_update


def create_consortium(context, consortium_name, org_names, mod_policy):
    channel = common_dot_configtx_pb2.ConfigGroup()
    directory = getDirectory(context=context)
    channel.groups[ConsortiumsGroup].groups[consortium_name].mod_policy = mod_policy
    # Add the orderer org groups MSPConfig info to consortiums group
    for consortium_org in [org for org in directory.getOrganizations().values() if org.name in org_names]:
        # channel.groups[ConsortiumsGroup].groups[consortium_name].groups[consortium_org.name].mod_policy = BootstrapHelper.KEY_POLICY_ADMINS
        channel.groups[ConsortiumsGroup].groups[consortium_name].groups[consortium_org.name].values[BootstrapHelper.KEY_MSP_INFO].value = toValue(
            get_msp_config(org=consortium_org, directory=directory))
        channel.groups[ConsortiumsGroup].groups[consortium_name].groups[consortium_org.name].values[BootstrapHelper.KEY_MSP_INFO].mod_policy=BootstrapHelper.KEY_POLICY_ADMINS
    typeImplicitMeta = common_dot_policies_pb2.Policy.PolicyType.Value("IMPLICIT_META")
    Policy = common_dot_policies_pb2.Policy
    IMP = common_dot_policies_pb2.ImplicitMetaPolicy
    ruleAny = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("ANY")
    ruleAll = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("ALL")
    ruleMajority = common_dot_policies_pb2.ImplicitMetaPolicy.Rule.Value("MAJORITY")
    channel.groups[ConsortiumsGroup].groups[consortium_name].values[BootstrapHelper.KEY_CHANNEL_CREATION_POLICY].value = toValue(
        Policy(type=typeImplicitMeta, value=IMP(
            rule=ruleAll, sub_policy=BootstrapHelper.KEY_POLICY_WRITERS).SerializeToString()))
    channel.groups[ConsortiumsGroup].groups[consortium_name].values[BootstrapHelper.KEY_CHANNEL_CREATION_POLICY].mod_policy=BootstrapHelper.KEY_POLICY_ADMINS
    # For now, setting same policies for each 'Non-Org' group
    orgs = [directory.getOrganization(orgName) for orgName in org_names]
    set_default_policies_for_orgs(channel.groups[ConsortiumsGroup], orgs, consortium_name, version=0, policy_version=0)
    return channel


def broadcast_channel_config_tx(context, certAlias, composeService, configTxEnvelope, user):
    dataFunc = lambda x: configTxEnvelope
    user.broadcastMessages(context=context, numMsgsToBroadcast=1, composeService=composeService,
                           dataFunc=dataFunc)

def get_latest_configuration_block(deliverer_stream_helper, channel_id):
    latest_config_block = None
    deliverer_stream_helper.seekToRange(chainID=channel_id, start="Newest", end="Newest")
    blocks = deliverer_stream_helper.getBlocks()
    assert len(blocks) == 1, "Expected single block, received: {0} blocks".format(len(blocks))
    newest_block = blocks[0]
    last_config = common_dot_common_pb2.LastConfig()
    metadata = common_dot_common_pb2.Metadata()
    metadata.ParseFromString(newest_block.metadata.metadata[common_dot_common_pb2.BlockMetadataIndex.Value('LAST_CONFIG')])
    last_config.ParseFromString(metadata.value)
    if last_config.index == newest_block.header.number:
        latest_config_block = newest_block
    else:
        deliverer_stream_helper.seekToRange(chainID=channel_id, start=last_config.index, end=last_config.index)
        blocks = deliverer_stream_helper.getBlocks()
        assert len(blocks) == 1, "Expected single block, received: {0} blocks".format(len(blocks))
        assert len(blocks[0].data.data) == 1, "Expected single transaction for configuration block, instead found {0} transactions".format(len(block.data.data))
        latest_config_block = blocks[0]
    return latest_config_block

class EnvelopeExractor:

    def __init__(self, envelope):
        self.envelope = envelope

        self.payload = common_dot_common_pb2.Payload()
        self.payload.ParseFromString(self.envelope.payload)

        self.channel_header = common_dot_common_pb2.ChannelHeader()
        self.channel_header.ParseFromString(self.payload.header.channel_header)

        self.signature_header = common_dot_common_pb2.SignatureHeader()
        self.signature_header.ParseFromString(self.payload.header.signature_header)

    def get_channel_header_type_name(self):
        return common_dot_common_pb2.HeaderType.Name(self.channel_header.type)

    def get_creator(self):
        serialized_identity = identities_pb2.SerializedIdentity()
        serialized_identity.ParseFromString(self.signature_header.creator)
        return serialized_identity


class BlockWrapper:

    def __init__(self, block):
        self.block = block
        self.envx_list = []
        for tx_bytes in block.data.data:
            envelope = common_dot_common_pb2.Envelope()
            envelope.ParseFromString(tx_bytes)
            envx = EnvelopeExractor(envelope)
            self.envx_list.append(envx)
        block.metadata.metadata[common_dot_common_pb2.BlockMetadataIndex.Value('TRANSACTIONS_FILTER')]




def get_channel_group_from_config_block(block):
    assert len(block.data.data) == 1, "Expected single transaction for configuration block, instead found {0} transactions".format(len(block.data.data))
    e = common_dot_common_pb2.Envelope()
    e.ParseFromString(block.data.data[0])
    envelope_extractor = EnvelopeExractor(e)
    assert envelope_extractor.channel_header.type == common_dot_common_pb2.HeaderType.Value('CONFIG'), "Expected a block with single TX of type CONFIG, got type {0}".format(common_dot_common_pb2.HeaderType.Name(envelope_extractor.channel_header.type))
    config_envelope = common_dot_configtx_pb2.ConfigEnvelope()
    config_envelope.ParseFromString(envelope_extractor.payload.data)
    return config_envelope.config.channel_group

def getArgsFromContextForUser(context, userName):
    directory = getDirectory(context)
    # Update the chaincodeSpec ctorMsg for invoke
    args = []
    if 'table' in context:
        if context.table:
            # There are function arguments
            user = directory.getUser(userName)
            # Allow the user to specify expressions referencing tags in the args list
            pattern = re.compile('\{(.*)\}$')
            for arg in context.table[0].cells:
                m = pattern.match(arg)
                if m:
                    # tagName reference found in args list
                    tagName = m.groups()[0]
                    # make sure the tagName is found in the users tags
                    assert tagName in user.tags, "TagName '{0}' not found for user '{1}'".format(tagName,
                                                                                                 user.getUserName())
                    args.append(user.tags[tagName])
                else:
                    # No tag referenced, pass the arg
                    args.append(arg)
    return args


def get_args_for_user(args_input, user):
    args = []
    pattern = re.compile('\{(.*)\}$')
    for arg in args_input:
        m = pattern.match(arg)
        if m:
            # tagName reference found in args list
            tagName = m.groups()[0]
            # make sure the tagName is found in the users tags
            assert tagName in user.tags, "TagName '{0}' not found for user '{1}'".format(tagName,
                                                                                         user.getUserName())
            args.append(user.tags[tagName])
        else:
            # No tag referenced, pass the arg
            args.append(arg)
    return tuple(args)


def get_config_update_from_envelope(config_update_envelope):
    config_update = common_dot_configtx_pb2.ConfigUpdate()
    config_update.ParseFromString(config_update_envelope.config_update)
    return config_update

def get_compose_service_by_organization(directory, discriminator):
    # Must first sort for groupby to work properly
    nats_sorted_by_org = sorted(directory.getNamedCtxTuples(), key=lambda x: x.organization)
    return groupby([(nat.organization, nat.nodeName) for nat in  nats_sorted_by_org if (discriminator in nat.nodeName) and ('signer' in nat.user.lower())], lambda x: x[0])


def add_org_to_channel(context, directory, requesting_config_admin_nat, signing_nats, org_to_add, channel_id, orderer_compose_service='orderer0'):
    contextHelper = ContextHelper.GetHelper(context=context)
    bootstrap_helper = contextHelper.get_bootstrap_helper()

    requesting_config_admin = directory.getUser(requesting_config_admin_nat.user)
    deliverer_stream_helper = requesting_config_admin.getDelivererStreamHelper(context, orderer_compose_service)
    latest_config_block = get_latest_configuration_block(deliverer_stream_helper, channel_id)
    latest_channel_group = get_channel_group_from_config_block(latest_config_block)

    read_set = common_dot_configtx_pb2.ConfigGroup()
    write_set = common_dot_configtx_pb2.ConfigGroup()

    read_set.CopyFrom(latest_channel_group)
    write_set.CopyFrom(read_set)

    # Add the MSP Config
    write_set.groups[ApplicationGroup].groups[org_to_add.name].values[bootstrap_helper.KEY_MSP_INFO].value = toValue(
        get_msp_config(org=org_to_add, directory=directory))
    write_set.groups[ApplicationGroup].groups[org_to_add.name].values[bootstrap_helper.KEY_MSP_INFO].mod_policy=bootstrap_helper.KEY_POLICY_ADMINS
    set_default_policies_for_orgs(channel=write_set, orgs=[org_to_add], group_name=ApplicationGroup)

    # Now increment the ApplicationGroup version because keyset changed
    write_set.groups[ApplicationGroup].version+=1

    config_update = common_dot_configtx_pb2.ConfigUpdate(channel_id=channel_id, read_set=read_set, write_set=write_set)
    config_update_envelope = create_config_update_envelope(config_update=config_update)

    #Now add the signature(s)
    for signing_nat in signing_nats:
        config_admin = directory.getUser(signing_nat.user)
        bootstrap_helper.add_signature_to_config_update_envelope(config_update_envelope, (config_admin, signing_nat.organization, directory.findCertForNodeAdminTuple(signing_nat)))

    envelope_for_config_update = create_envelope_for_msg(directory=directory,
                                                         nodeAdminTuple=requesting_config_admin_nat,
                                                         chainId=channel_id,
                                                         msg=config_update_envelope,
                                                         typeAsString="CONFIG_UPDATE")
    # Now broadcast to orderer
    broadcast_channel_config_tx(context=context, certAlias=None, composeService=orderer_compose_service, user=requesting_config_admin,
                                configTxEnvelope=envelope_for_config_update)

def get_channel_names_for_channel(context, user_name, service_name, channel_id_or_ref):
    directory = getDirectory(context)
    user = directory.getUser(userName=user_name)
    (channel_id,) = get_args_for_user([channel_id_or_ref], user)
    deliverer_stream_helper = user.getDelivererStreamHelper(context, service_name)
    deliverer_stream_helper.seekToRange(chainID=channel_id, start="Oldest", end="Newest")
    blocks = deliverer_stream_helper.getBlocks()
    block_wrappers = [BlockWrapper(b) for b in blocks]
    # Get all of the ORDERER_TRANSACTION type envelopes to get the list of channels referenced.
    envx_list = [envx for bw in block_wrappers for envx in bw.envx_list if envx.get_channel_header_type_name()=="ORDERER_TRANSACTION"]
    channel_names_duplicates = []
    for envx in envx_list:
        env = common_dot_common_pb2.Envelope()
        env.ParseFromString(envx.payload.data)
        payload = common_dot_common_pb2.Payload()
        payload.ParseFromString(env.payload)
        ch = common_dot_common_pb2.ChannelHeader()
        ch.ParseFromString(payload.header.channel_header)
        channel_names_duplicates.append(ch.channel_id)
    channel_ids = list(dict.fromkeys(channel_names_duplicates))
    return channel_ids