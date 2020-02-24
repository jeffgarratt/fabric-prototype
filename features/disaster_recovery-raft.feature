# Copyright IBM Corp. 2016 All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#

# Test Bootstrap function
#
# Tags that can be used and will affect test internals:
#  @doNotDecompose will NOT decompose the named compose_yaml after scenario ends.  Useful for setting up environment and reviewing after scenario.
#
#  @generateDocs will generate documentation for the scenario that can be used for both verification and comprehension.
#

@disaster_recovery
Feature: Disaster Recovery
  As a blockchain entrepreneur
  I want to bootstrap a new blockchain network and verify disaster recovery mechanisms

    @doNotDecompose
    @generateDocs
    Scenario Outline: Demonstrate disaster recovery for a network with 4 peers (2 orgs)  and 1 orderer (1 org), each having a single independent root of trust (No fabric-ca, just openssl)
      #creates 1 self-signed key/cert pair per orderer organization
      Given the orderer network has organizations:
        | Organization | Readers | Writers | Admins |
        | ordererOrg0  | member  | member  | admin  |
        | ordererOrg1  | member  | member  | admin  |

      And user requests role of orderer admin by creating a key and csr for orderer and acquires signed certificate from organization:
        | User                   | Orderer     | Organization | AliasSavedUnder   |
        | orderer0Signer         | orderer0    | ordererOrg0  |                   |
        | orderer1Signer         | orderer1    | ordererOrg0  |                   |
        | orderer2Signer         | orderer2    | ordererOrg1  |                   |
        | orderer0Admin          | orderer0    | ordererOrg0  |                   |
        | orderer1Admin          | orderer1    | ordererOrg0  |                   |
        | orderer2Admin          | orderer2    | ordererOrg1  |                   |
        | configAdminOrdererOrg0 | configAdmin | ordererOrg0  | config-admin-cert |
        | configAdminOrdererOrg1 | configAdmin | ordererOrg1  | config-admin-cert |


      # Rolenames : MspPrincipal.proto
      And the peer network has organizations:
        | Organization | Readers | Writers | Admins |
        | peerOrg0     | member  | member  | admin  |
        | peerOrg1     | member  | member  | admin  |
        | peerOrg2     | member  | member  | admin  |

      And a ordererBootstrapAdmin is identified and given access to all public certificates and orderer node info

      And the ordererBootstrapAdmin creates a cert alias "bootstrapCertAlias" for orderer network bootstrap purposes for organizations
        | Organization |
        | ordererOrg0  |

      And the ordererBootstrapAdmin generates a GUUID to identify the orderer system chain and refer to it by name as "ordererSystemChannelId"

    # We now have an orderer network with NO peers.  Now need to configure and start the peer network
    # This can be currently automated through folder creation of the proper form and placing PEMs.
      And user requests role for peer by creating a key and csr for peer and acquires signed certificate from organization:
        | User                | Peer        | Organization | AliasSavedUnder   |
        | peer0Signer         | peer0       | peerOrg0     |                   |
        | peer1Signer         | peer1       | peerOrg0     |                   |
        | peer2Signer         | peer2       | peerOrg1     |                   |
        | peer3Signer         | peer3       | peerOrg1     |                   |
        | peer4Signer         | peer4       | peerOrg2     |                   |
        | peer0Admin          | peer0       | peerOrg0     | peer-admin-cert   |
        | peer1Admin          | peer1       | peerOrg0     | peer-admin-cert   |
        | peer2Admin          | peer2       | peerOrg1     | peer-admin-cert   |
        | peer3Admin          | peer3       | peerOrg1     | peer-admin-cert   |
        | peer4Admin          | peer4       | peerOrg2     | peer-admin-cert   |
        | configAdminPeerOrg0 | configAdmin | peerOrg0     | config-admin-cert |
        | configAdminPeerOrg1 | configAdmin | peerOrg1     | config-admin-cert |
        | configAdminPeerOrg2 | configAdmin | peerOrg2     | config-admin-cert |

    # Order info includes orderer admin/orderer information and address (host:port) from previous steps
    # Only the peer organizations can vary.
      And the ordererBootstrapAdmin using cert alias "bootstrapCertAlias" creates the genesis block "ordererGenesisBlock" for chain "ordererSystemChannelId" for composition "<ComposeFile>" and consensus "<ConsensusType>" with consortiums modification policy "/Channel/Orderer/Admins" using consortiums:
        | Consortium |
#      | consortium1 |


      And the orderer admins inspect and approve the genesis block for chain "ordererSystemChannelId"

    # to be used for setting the orderer genesis block path parameter in composition
      And the orderer admins use the genesis block for chain "ordererSystemChannelId" to configure orderers


      And we set the base fabric version to "<FabricBaseVersion>"

      And we compose "<ComposeFile>"


    # Sleep as to allow system up time
      And I wait "<SystemUpWaitTime>" seconds

      Given user "ordererBootstrapAdmin" gives "ordererSystemChannelId" to user "configAdminOrdererOrg0" who saves it as "ordererSystemChannelId"
      And user "ordererBootstrapAdmin" gives "ordererGenesisBlock" to user "configAdminOrdererOrg0" who saves it as "ordererGenesisBlock"

      And the orderer config admin "configAdminOrdererOrg0" creates a consortium "consortium1" with modification policy "/Channel/Orderer/Admins" for peer orgs who wish to form a network:
        | Organization |
        | peerOrg0     |
        | peerOrg1     |
        | peerOrg2     |

      And user "configAdminOrdererOrg0" using cert alias "config-admin-cert" connects to deliver function on node "<orderer0>" using port "7050"

      And user "configAdminOrdererOrg0" retrieves the latest config update "latestOrdererConfig" from orderer "<orderer0>" for channel "{ordererSystemChannelId}"

      And the orderer config admin "configAdminOrdererOrg0" creates a consortiums config update "consortiumsConfigUpdate1" using config "latestOrdererConfig" using orderer system channel ID "ordererSystemChannelId" to add consortiums:
        | Consortium  |
        | consortium1 |

      And the user "configAdminOrdererOrg0" creates a configUpdateEnvelope "consortiumsConfigUpdate1Envelope" using configUpdate "consortiumsConfigUpdate1"

      And the user "configAdminOrdererOrg0" collects signatures for ConfigUpdateEnvelope "consortiumsConfigUpdate1Envelope" from developers:
        | Developer              | Cert Alias        |
        | configAdminOrdererOrg0 | config-admin-cert |
        | configAdminOrdererOrg1 | config-admin-cert |

      And the user "configAdminOrdererOrg0" creates a ConfigUpdate Tx "consortiumsConfigUpdateTx1" using cert alias "config-admin-cert" using signed ConfigUpdateEnvelope "consortiumsConfigUpdate1Envelope"

      And the user "configAdminOrdererOrg0" using cert alias "config-admin-cert" broadcasts ConfigUpdate Tx "consortiumsConfigUpdateTx1" to orderer "<orderer0>"


      Given the following application developers are defined for peer organizations and each saves their cert as alias
        | Developer | Consortium  | Organization | AliasSavedUnder  |
        | dev0Org0  | consortium1 | peerOrg0     | consortium1-cert |
        | dev0Org1  | consortium1 | peerOrg1     | consortium1-cert |

      And user "configAdminOrdererOrg0" gives "consortium1" to user "dev0Org0" who saves it as "consortium1"

      And the user "dev0Org0" creates a peer organization set "peerOrgSet1" with peer organizations:
        | Organization |
        | peerOrg0     |
        | peerOrg1     |
#      |  peerOrg2     |

      And the user "dev0Org0" creates an peer anchor set "anchors1" for orgs:
        | User        | Peer  | Organization |
        | peer0Signer | peer0 | peerOrg0     |
        | peer2Signer | peer2 | peerOrg1     |

    # Entry point for creating a channel
      And the user "dev0Org0" creates a new channel ConfigUpdate "createChannelConfigUpdate1" using consortium "consortium1"
        | ChannelID                         | PeerOrgSet  | [PeerAnchorSet] |
        | com.acme.blockchain.jdoe.channel1 | peerOrgSet1 |                 |

      And the user "dev0Org0" creates a configUpdateEnvelope "createChannelConfigUpdate1Envelope" using configUpdate "createChannelConfigUpdate1"


      And the user "dev0Org0" collects signatures for ConfigUpdateEnvelope "createChannelConfigUpdate1Envelope" from developers:
        | Developer | Cert Alias       |
        | dev0Org0  | consortium1-cert |
        | dev0Org1  | consortium1-cert |

      And the user "dev0Org0" creates a ConfigUpdate Tx "configUpdateTx1" using cert alias "consortium1-cert" using signed ConfigUpdateEnvelope "createChannelConfigUpdate1Envelope"

      And the user "dev0Org0" using cert alias "consortium1-cert" broadcasts ConfigUpdate Tx "configUpdateTx1" to orderer "<orderer0>"


    # Sleep as the local orderer needs to bring up the resources that correspond to the new channel
    # For the Kafka orderer, this includes setting up a producer and consumer for the channel's partition
    # Requesting a deliver earlier may result in a SERVICE_UNAVAILABLE response and a connection drop
      And I wait "<ChannelJoinDelay>" seconds

      When user "dev0Org0" using cert alias "consortium1-cert" connects to deliver function on node "<orderer0>" using port "7050"
      And user "dev0Org0" sends deliver a seek request on node "<orderer0>" with properties:
        | ChainId                           | Start | End |
        | com.acme.blockchain.jdoe.channel1 | 0     | 0   |

      Then user "dev0Org0" should get a delivery "genesisBlockForMyNewChannel" from "<orderer0>" of "1" blocks with "1" messages within "1" seconds

      Given user "dev0Org0" gives "genesisBlockForMyNewChannel" to user "dev0Org1" who saves it as "genesisBlockForMyNewChannel"

      Given user "dev0Org0" gives "genesisBlockForMyNewChannel" to user "peer0Admin" who saves it as "genesisBlockForMyNewChannel"
      Given user "dev0Org0" gives "genesisBlockForMyNewChannel" to user "peer1Admin" who saves it as "genesisBlockForMyNewChannel"


    # This is entry point for joining an existing channel
      When user "peer0Admin" using cert alias "peer-admin-cert" requests to join channel using genesis block "genesisBlockForMyNewChannel" on peers with result "joinChannelResult"
        | Peer  |
        | peer0 |

      Then user "peer0Admin" expects result code for "joinChannelResult" of "200" from peers:
        | Peer  |
        | peer0 |

      When user "peer1Admin" using cert alias "peer-admin-cert" requests to join channel using genesis block "genesisBlockForMyNewChannel" on peers with result "joinChannelResult"
        | Peer  |
        | peer1 |

      Then user "peer1Admin" expects result code for "joinChannelResult" of "200" from peers:
        | Peer  |
        | peer1 |


      Given the user "configAdminPeerOrg0" creates an peer anchor set "anchors1" for orgs:
        | User        | Peer  | Organization |
        | peer0Signer | peer0 | peerOrg0     |

      And user "configAdminPeerOrg0" using cert alias "config-admin-cert" connects to deliver function on node "<orderer0>" using port "7050"

      And user "configAdminPeerOrg0" retrieves the latest config update "latestChannelConfigUpdate" from orderer "<orderer0>" for channel "com.acme.blockchain.jdoe.channel1"

      And the user "configAdminPeerOrg0" creates an existing channel config update "existingChannelConfigUpdate1" using config update "latestChannelConfigUpdate"
        | ChannelID                         | [PeerAnchorSet] |
        | com.acme.blockchain.jdoe.channel1 | anchors1        |






      Given the user "configAdminPeerOrg0" creates a configUpdateEnvelope "existingChannelConfigUpdate1Envelope" using configUpdate "existingChannelConfigUpdate1"


      And the user "configAdminPeerOrg0" collects signatures for ConfigUpdateEnvelope "existingChannelConfigUpdate1Envelope" from developers:
        | Developer           | Cert Alias        |
        | configAdminPeerOrg0 | config-admin-cert |

      And the user "configAdminPeerOrg0" creates a ConfigUpdate Tx "existingChannelConfigUpdateTx1" using cert alias "config-admin-cert" using signed ConfigUpdateEnvelope "existingChannelConfigUpdate1Envelope"


      When the user "configAdminPeerOrg0" broadcasts transaction "existingChannelConfigUpdateTx1" to orderer "<orderer0>"

      And I wait "<BroadcastWaitTime>" seconds

      And user "configAdminPeerOrg0" sends deliver a seek request on node "<orderer0>" with properties:
        | ChainId                           | Start | End |
        | com.acme.blockchain.jdoe.channel1 | 1     | 1   |

      Then user "configAdminPeerOrg0" should get a delivery "deliveredExistingChannelConfigUpdateTx1Block" from "<orderer0>" of "1" blocks with "1" messages within "1" seconds


#    And I quit

      Given user "dev0Org1" gives "genesisBlockForMyNewChannel" to user "peer2Admin" who saves it as "genesisBlockForMyNewChannel"
      Given user "dev0Org1" gives "genesisBlockForMyNewChannel" to user "peer3Admin" who saves it as "genesisBlockForMyNewChannel"

      When user "peer2Admin" using cert alias "peer-admin-cert" requests to join channel using genesis block "genesisBlockForMyNewChannel" on peers with result "joinChannelResult"
        | Peer  |
        | peer2 |

      Then user "peer2Admin" expects result code for "joinChannelResult" of "200" from peers:
        | Peer  |
        | peer2 |

      When user "peer3Admin" using cert alias "peer-admin-cert" requests to join channel using genesis block "genesisBlockForMyNewChannel" on peers with result "joinChannelResult"
        | Peer  |
        | peer3 |

      Then user "peer3Admin" expects result code for "joinChannelResult" of "200" from peers:
        | Peer  |
        | peer3 |


#      #######################################################
#      #
#      # Add peerOrg2 to channel
#      #
#      #######################################################
#      When the user "configAdminPeerOrg0" using cert alias "config-admin-cert" adds organization "peerOrg2" to channel "com.acme.blockchain.jdoe.channel1" using orderer "orderer0" collecting signatures from:
#        | User                | Cert Alias        |
#        | configAdminPeerOrg0 | config-admin-cert |
#        | configAdminPeerOrg1 | config-admin-cert |
#
#      And I wait "<BroadcastWaitTime>" seconds
#      # Had to add a wait as instantiation would fail with variant response bytes due to MSP cache not be updated in some cases.
#      And I wait "3" seconds
#
#
#      Given user "dev0Org0" gives "genesisBlockForMyNewChannel" to user "peer4Admin" who saves it as "genesisBlockForMyNewChannel"
#    # This is entry point for joining an existing channel
#      When user "peer4Admin" using cert alias "peer-admin-cert" requests to join channel using genesis block "genesisBlockForMyNewChannel" on peers with result "joinChannelResult"
#        | Peer  |
#        | peer4 |
#
#      Then user "peer4Admin" expects result code for "joinChannelResult" of "200" from peers:
#        | Peer  |
#        | peer4 |


      # Uncomment this if you wish to stop with just a channel created and joined on all peers
#      And we stop


      Given the user "configAdminPeerOrg1" creates an peer anchor set "anchors1" for orgs:
        | User        | Peer  | Organization |
        | peer2Signer | peer2 | peerOrg1     |




      #########################################################################
      #
      #  Demonstrate retrieving the latest block from the peer using deliver interface
      #
      #########################################################################
#      When user "dev0Org0" using cert alias "consortium1-cert" connects to deliver function on node "peer0" using port "7051"
#      And user "dev0Org0" sends deliver a seek request on node "peer0" with properties:
#        | ChainId                               | Start |  End    |
#        | com.acme.blockchain.jdoe.channel1     |   0   |  0      |
#
#      Then user "dev0Org0" should get a delivery "genesisBlockForMyNewChannelFromPeer" from "peer0" of "1" blocks with "1" messages within "1" seconds
#
#      When user "dev0Org0" using cert alias "consortium1-cert" connects to deliver function on node "peer2" using port "7051"
#      And user "dev0Org0" sends deliver a seek request on node "peer2" with properties:
#        | ChainId                               | Start |  End    |
#        | com.acme.blockchain.jdoe.channel1     |   0   |  0      |
#
#      Then user "dev0Org0" should get a delivery "genesisBlockForMyNewChannelFromOtherOrgsPeer" from "peer2" of "1" blocks with "1" messages within "1" seconds


      ###########################################################################
      #
      # Config_update to system channel for group /Channel/Orderer with new value 'Capabilities'
      #
      ###########################################################################
      Given user "configAdminOrdererOrg0" using cert alias "config-admin-cert" connects to deliver function on node "<orderer0>" using port "7050"
      And user "configAdminOrdererOrg0" retrieves the latest config update "latestOrdererConfigForCapabilitiesChange" from orderer "<orderer0>" for channel "{ordererSystemChannelId}"
      And user "configAdminOrdererOrg0" creates a capabilities config update "capabilitiesV1.1ConfigUpdateForOrderer" using config "latestOrdererConfigForCapabilitiesChange" using channel ID "{ordererSystemChannelId}" with mod policy "Admins" to add capabilities:
        | Group            | Capabilities |
        | /Channel/Orderer | V1_4_2       |
      And the user "configAdminOrdererOrg0" creates a configUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer" using configUpdate "capabilitiesV1.1ConfigUpdateForOrderer"

      And the user "configAdminOrdererOrg0" collects signatures for ConfigUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer" from developers:
        | Developer              | Cert Alias        |
        | configAdminOrdererOrg0 | config-admin-cert |
        | configAdminOrdererOrg1 | config-admin-cert |

      And the user "configAdminOrdererOrg0" creates a ConfigUpdate Tx "capabilitiesConfigUpdateTx1" using cert alias "config-admin-cert" using signed ConfigUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer"

      And the user "configAdminOrdererOrg0" using cert alias "config-admin-cert" broadcasts ConfigUpdate Tx "capabilitiesConfigUpdateTx1" to orderer "<orderer0>"

      And I wait "<BroadcastWaitTime>" seconds


      ###########################################################################
      #
      # Config_update to system channel for group /Channel with new value 'Capabilities'
      #
      ###########################################################################
      Given user "configAdminOrdererOrg0" retrieves the latest config update "latestOrdererConfigForCapabilitiesChange2" from orderer "<orderer0>" for channel "{ordererSystemChannelId}"
      And user "configAdminOrdererOrg0" creates a capabilities config update "capabilitiesV1.1ConfigUpdateForOrderer2" using config "latestOrdererConfigForCapabilitiesChange2" using channel ID "{ordererSystemChannelId}" with mod policy "Admins" to add capabilities:
        | Group    | Capabilities |
        | /Channel | V1_4_3       |
      And the user "configAdminOrdererOrg0" creates a configUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer2" using configUpdate "capabilitiesV1.1ConfigUpdateForOrderer2"

      And the user "configAdminOrdererOrg0" collects signatures for ConfigUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer2" from developers:
        | Developer              | Cert Alias        |
        | configAdminOrdererOrg0 | config-admin-cert |
        | configAdminOrdererOrg1 | config-admin-cert |

      And the user "configAdminOrdererOrg0" creates a ConfigUpdate Tx "capabilitiesConfigUpdateTx2" using cert alias "config-admin-cert" using signed ConfigUpdateEnvelope "capabilitiesV1.1ConfigUpdateEnvelopeForOrderer2"

      And the user "configAdminOrdererOrg0" using cert alias "config-admin-cert" broadcasts ConfigUpdate Tx "capabilitiesConfigUpdateTx2" to orderer "<orderer0>"

      And I wait "<BroadcastWaitTime>" seconds


      ###########################################################################
      #
      # Config_update to system channel to put system into maintenance mode.
      #
      ###########################################################################
      Given user "configAdminOrdererOrg0" retrieves the latest config update "latestOrdererConfigForConensusStateMaint" from orderer "<orderer0>" for channel "{ordererSystemChannelId}"
      And the orderer config admin "configAdminOrdererOrg0" creates a consensus state update "consensusStateMaintConfigUpdate1" using config "latestOrdererConfigForConensusStateMaint" using orderer system channel ID "ordererSystemChannelId" to change state to "STATE_MAINTENANCE"
      And the user "configAdminOrdererOrg0" creates a configUpdateEnvelope "consensusStateConfigUpdate1Envelope" using configUpdate "consensusStateMaintConfigUpdate1"

      And the user "configAdminOrdererOrg0" collects signatures for ConfigUpdateEnvelope "consensusStateConfigUpdate1Envelope" from developers:
        | Developer              | Cert Alias        |
        | configAdminOrdererOrg0 | config-admin-cert |
        | configAdminOrdererOrg1 | config-admin-cert |

      And the user "configAdminOrdererOrg0" creates a ConfigUpdate Tx "consensusStateConfigUpdateTx1" using cert alias "config-admin-cert" using signed ConfigUpdateEnvelope "consensusStateConfigUpdate1Envelope"

      And the user "configAdminOrdererOrg0" using cert alias "config-admin-cert" broadcasts ConfigUpdate Tx "consensusStateConfigUpdateTx1" to orderer "<orderer0>"

      And I wait "<BroadcastWaitTime>" seconds


      Given user "configAdminOrdererOrg0" retrieves the list of channel names "channelNamesFromOrdererSystemChannel" from orderer "<orderer0>" for orderer system channel "{ordererSystemChannelId}"



      When user "peer0Admin" creates a chaincode spec "ccSpec" with name "fabcar" and version "1.0" of type "GOLANG" for chaincode "github.com/hyperledger/fabric-samples/chaincode/fabcar/go" with args
        | funcName | arg1 | arg2 | arg3 | arg4 |
#        | init     | a    | 100  | b    | 200  |

      # TODO: Will soon need to collect signatures (owners) and create a SignedChaincodeDeploymentSpec which will supplant the payload for installProposal.

      # Under the covers, create a deployment spec, etc.
      And user "peer0Admin" using cert alias "peer-admin-cert" creates a install proposal "installProposal1" using chaincode spec "ccSpec"

      And user "peer0Admin" using cert alias "peer-admin-cert" sends proposal "installProposal1" to endorsers with timeout of "90" seconds with proposal responses "installProposalResponses":
        | Endorser |
        | peer0    |

      Then user "peer0Admin" expects proposal responses "installProposalResponses" with status "200" from endorsers:
        | Endorser |
        | peer0    |

      Given user "peer0Admin" gives "ccSpec" to user "peer2Admin" who saves it as "ccSpec"

      When user "peer2Admin" using cert alias "peer-admin-cert" creates a install proposal "installProposal1" using chaincode spec "ccSpec"

      And user "peer2Admin" using cert alias "peer-admin-cert" sends proposal "installProposal1" to endorsers with timeout of "90" seconds with proposal responses "installProposalResponses":
        | Endorser |
        | peer2    |

      Then user "peer2Admin" expects proposal responses "installProposalResponses" with status "200" from endorsers:
        | Endorser |
        | peer2    |




      Given user "peer0Admin" gives "ccSpec" to user "dev0Org0" who saves it as "ccSpec"
      And user "peer0Admin" gives "ccSpec" to user "configAdminPeerOrg0" who saves it as "ccSpec"

      And user "configAdminPeerOrg0" creates a signature policy envelope "signedByMemberOfPeerOrg0AndPeerOrg1" using "envelope(n_out_of(2,[signed_by(0),signed_by(1)]),[member('peerOrg0'), member('peerOrg1')])"

      When user "configAdminPeerOrg0" using cert alias "config-admin-cert" creates a instantiate proposal "instantiateProposal1" for channel "com.acme.blockchain.jdoe.channel1" using chaincode spec "ccSpec" and endorsement policy "signedByMemberOfPeerOrg0AndPeerOrg1"

      And user "configAdminPeerOrg0" using cert alias "config-admin-cert" sends proposal "instantiateProposal1" to endorsers with timeout of "90" seconds with proposal responses "instantiateProposalResponses":
        | Endorser |
        | peer0    |
        | peer2    |


      Then user "configAdminPeerOrg0" expects proposal responses "instantiateProposalResponses" with status "200" from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |

      And user "configAdminPeerOrg0" expects proposal responses "instantiateProposalResponses" each have the same value from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |



      When the user "configAdminPeerOrg0" creates transaction "instantiateTx1" from proposal "instantiateProposal1" and proposal responses "instantiateProposalResponses" for channel "com.acme.blockchain.jdoe.channel1"

      And the user "configAdminPeerOrg0" broadcasts transaction "instantiateTx1" to orderer "<orderer1>"

      # Sleep as the local orderer ledger needs to create the block that corresponds to the start number of the seek request
      And I wait "2" seconds

      And user "configAdminPeerOrg0" sends deliver a seek request on node "<orderer0>" with properties:
        | ChainId                           | Start | End |
        | com.acme.blockchain.jdoe.channel1 | 2     | 2   |

      Then user "configAdminPeerOrg0" should get a delivery "deliveredInstantiateTx1Block" from "<orderer0>" of "1" blocks with "1" messages within "1" seconds

      And I quit


      # Sleep to allow for chaincode instantiation on the peer
      And I wait "5" seconds


      Given all users disconnect from orderers
      And we take snapshot "snapshot1" for the following orderers:
        | Orderer  |
        | orderer0 |

      And I quit


#      And the ordererBootstrapAdmin takes a snapshot "snapshot1" of the orderer system
      And user "configAdminPeerOrg0" using cert alias "config-admin-cert" connects to deliver function on node "<orderer0>" using port "7050"
      And user "dev0Org0" using cert alias "consortium1-cert" connects to deliver function on node "<orderer0>" using port "7050"

      Given we take snapshot "snapshot1" for the following peers:
        | Peer  |
        | peer0 |
        | peer1 |
        | peer2 |
        | peer3 |
        | peer4 |
      # Sleep as to allow system up time
      And I wait "<SystemUpWaitTime>" seconds



      # Entry point for invoking on an existing channel
      When user "dev0Org0" creates a chaincode invocation spec "querySpec1" using spec "ccSpec" with input:
        | funcName | arg1 |
        | query    | a    |

      # Under the covers, create a deployment spec, etc.
      And user "dev0Org0" using cert alias "consortium1-cert" creates a proposal "queryProposal1" for channel "com.acme.blockchain.jdoe.channel1" using chaincode spec "querySpec1"

      And user "dev0Org0" using cert alias "consortium1-cert" sends proposal "queryProposal1" to endorsers with timeout of "30" seconds with proposal responses "queryProposal1Responses":
        | Endorser |
        | peer0    |
        | peer2    |

      Then user "dev0Org0" expects proposal responses "queryProposal1Responses" with status "200" from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |

      And user "dev0Org0" expects proposal responses "queryProposal1Responses" each have the same value from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |


      # Entry point for invoking on an existing channel
      When user "dev0Org0" creates a chaincode invocation spec "invocationSpec1" using spec "ccSpec" with input:
        | funcName | arg1 | arg2 | arg3 |
        | invoke   | a    | b    | 10   |

      # Under the covers, create a deployment spec, etc.
      And user "dev0Org0" using cert alias "consortium1-cert" creates a proposal "invokeProposal1" for channel "com.acme.blockchain.jdoe.channel1" using chaincode spec "invocationSpec1"

      And user "dev0Org0" using cert alias "consortium1-cert" sends proposal "invokeProposal1" to endorsers with timeout of "30" seconds with proposal responses "invokeProposal1Responses":
        | Endorser |
        | peer0    |
        | peer2    |

      Then user "dev0Org0" expects proposal responses "invokeProposal1Responses" with status "200" from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |

      And user "dev0Org0" expects proposal responses "invokeProposal1Responses" each have the same value from endorsers:
        | Endorser |
        | peer0    |
        | peer2    |

      When the user "dev0Org0" creates transaction "invokeTx1" from proposal "invokeProposal1" and proposal responses "invokeProposal1Responses" for channel "com.acme.blockchain.jdoe.channel1"

      And the user "dev0Org0" broadcasts transaction "invokeTx1" to orderer "<orderer2>"

      # Sleep as the local orderer ledger needs to create the block that corresponds to the start number of the seek request
      And I wait "<BroadcastWaitTime>" seconds

      And user "dev0Org0" sends deliver a seek request on node "<orderer0>" with properties:
        | ChainId                           | Start | End |
        | com.acme.blockchain.jdoe.channel1 | 3     | 3   |

      Then user "dev0Org0" should get a delivery "deliveredInvokeTx1Block" from "<orderer0>" of "1" blocks with "1" messages within "1" seconds


      Given all users disconnect from orderers
      And the ordererBootstrapAdmin takes a snapshot "snapshot2" of the orderer system
      And user "configAdminPeerOrg0" using cert alias "config-admin-cert" connects to deliver function on node "<orderer0>" using port "7050"
      And user "dev0Org0" using cert alias "consortium1-cert" connects to deliver function on node "<orderer0>" using port "7050"

      Given we take snapshot "snapshot2" for the following peers:
        | Peer  |
        | peer0 |
        | peer1 |
        | peer2 |
        | peer3 |
        | peer4 |
      # Sleep as to allow system up time
      And I wait "<SystemUpWaitTime>" seconds


      # TODO: Once events are working, consider listen event listener as well.

      Examples: Orderer Options
        | ComposeFile                   | SystemUpWaitTime | ConsensusType | ChannelJoinDelay | BroadcastWaitTime | orderer0 | orderer1 | orderer2 | Orderer Specific Info | FabricBaseVersion |
        | dc-disaster-recovery-raft.yml | 1                | etcdraft      | 2                | .25               | orderer0 | orderer1 | orderer2 |                       | 2.0               |
#        | dc-base.yml  dc-peer-couchdb.yml                      | 10               | solo          | 2                | 2                 | orderer0 | orderer0 | orderer0 |                       | latest            |
