#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from copy import deepcopy
import math
from decimal import *
import logging
import numpy
import theano
from theanolm.network import RecurrentState

class LatticeDecoder(object):
    """Word Lattice Decoding Using a Neural Network Language Model
    """

    class Token:
        """Decoding Token

        A token represents a partial path through a word lattice. The decoder
        propagates a set of tokens through the lattice by
        """

        def __init__(self,
                     history=[],
                     state=[],
                     ac_logprob=0.0,
                     lat_lm_logprob=0.0,
                     nn_lm_logprob=0.0):
            """Constructs a token with given recurrent state and logprobs.

            :type history: list of ints
            :param history: word IDs that the token has passed

            :type state: RecurrentState
            :param state: the state of the recurrent layers for a single
                          sequence

            :type ac_logprob: float
            :param ac_logprob: sum of the acoustic log probabilities of the
                               lattice links

            :type lat_lm_logprob: float
            :param lat_lm_logprob: sum of the LM log probabilities of the
                                   lattice links

            :type nn_lm_logprob: float
            :param nn_lm_logprob: sum of the NNLM log probabilities of the
                                  lattice links
            """

            self.history = history
            self.state = state
            self.ac_logprob = ac_logprob
            self.lat_lm_logprob = lat_lm_logprob
            self.nn_lm_logprob = nn_lm_logprob

        @classmethod
        def copy(classname, token):
            """Creates a copy of a token.

            The recurrent layer states will not be copied - a pointer will be
            copied instead. There's no need to copy the structure, since we
            never modify the state of a token, but replace it if necessary.

            :type token: LatticeDecoder.Token
            :param token: a token to copy

            :rtype: LatticeDecoder.Token
            :returns: a copy of ``token``
            """

            return classname(deepcopy(token.history),
                             token.state,
                             token.ac_logprob,
                             token.lat_lm_logprob,
                             token.nn_lm_logprob)

        def compute_total_logprob(self, nn_lm_weight=1.0, lm_scale=1.0):
            """Computes the total log probability of the token by interpolating
            the LM logprobs, applying LM scale, and adding the acoustic logprob.

            :type nn_lm_weight: float
            :param nn_lm_weight: weight of the neural network LM probability
                                 when interpolating with the lattice probability

            :type lm_scale: float
            :param lm_scale: scaling factor for LM probability when computing
                             the total probability
            """

            lat_lm_prob = math.exp(self.lat_lm_logprob)
            nn_lm_prob = math.exp(self.nn_lm_logprob)
            if (lat_lm_prob > 0) and (nn_lm_prob > 0):
                lm_prob = (1.0 - nn_lm_weight) * lat_lm_prob
                lm_prob += nn_lm_weight * nn_lm_prob
                lm_logprob = math.log(lm_prob)
            else:
                # An exp() resulted in an underflow. Use the decimal library.
                getcontext().prec = 16
                d_nn_lm_weight = Decimal(nn_lm_weight)
                d_inv_nn_lm_weight = Decimal(1.0) - d_nn_lm_weight
                d_lat_lm_logprob = Decimal(self.lat_lm_logprob)
                d_nn_lm_logprob = Decimal(self.nn_lm_logprob)
                d_lm_prob = d_inv_nn_lm_weight * d_lat_lm_logprob.exp()
                d_lm_prob += d_nn_lm_weight * d_nn_lm_logprob.exp()
                lm_logprob = float(d_lm_prob.ln())
            self.total_logprob = self.ac_logprob + (lm_logprob * lm_scale)

        def __str__(self, vocabulary=None):
            if vocabulary is None:
                history = ' '.join(str(x) for x in self.history)
            else:
                history = ' '.join(vocabulary.id_to_word[self.history])
            return '[{}]  acoustic: {:.2f}  lattice LM: {:.2f}  NNLM: ' \
                   '{:.2f}  total: {:.2f}'.format(
                   history,
                   self.ac_logprob,
                   self.lat_lm_logprob,
                   self.nn_lm_logprob,
                   self.total_logprob)

    def __init__(self, network, weight=1.0, ignore_unk=False, unk_penalty=None,
                 profile=False):
        """Creates a Theano function that computes the output probabilities for
        a single time step.

        Creates the function self.step_function that takes as input a set of
        word sequences and the current recurrent states. It uses the previous
        states and word IDs to compute the output distributions, and computes
        the probabilities of the target words.

        :type network: Network
        :param network: the neural network object

        :type weight: float
        :param weight: weight of the neural network probabilities when
                       interpolating with the lattice probabilities

        :type ignore_unk: bool
        :param ignore_unk: if set to True, <unk> tokens are excluded from
                           perplexity computation

        :type unk_penalty: float
        :param unk_penalty: if set to othern than None, used as <unk> token
                            score

        :type profile: bool
        :param profile: if set to True, creates a Theano profile object
        """

        self._network = network
        self._vocabulary = network.vocabulary
        self._weight = weight

        self._sos_id = self._vocabulary.word_to_id['<s>']
        self._eos_id = self._vocabulary.word_to_id['</s>']

        inputs = [network.word_input, network.class_input]
        inputs.extend(network.recurrent_state_input)
        inputs.append(network.target_class_ids)

        outputs = [network.target_probs()]
        outputs.extend(network.recurrent_state_output)

        # Ignore unused input, because is_training is only used by dropout
        # layer.
        self.step_function = theano.function(
            inputs,
            outputs,
            givens=[(network.is_training, numpy.int8(0))],
            name='step_predictor',
            on_unused_input='ignore')

    def decode(self, lattice):
        """Propagates tokens through given lattice and returns a list of tokens
        in the final node.

        Propagates tokens at a node to every outgoing link by creating a copy of
        each token and updating the language model scores according to the link.

        Lattices may contain !NULL, !ENTER, !EXIT, etc. nodes that model e.g.
        silence or sentence start or end, or for example when the topology is
        easier to represent with extra nodes. Such null nodes may contain
        language model scores. Then the function will update the lattice LM
        score, but will not compute anything with the neural network.

        :type lattice: Lattice
        :param lattice: a word lattice to be decoded

        :rtype: list of LatticeDecoder.Tokens
        :returns: the final tokens sorted by total log probability in descending
                  order
        """

        tokens = [list() for _ in lattice.nodes]
        initial_state = RecurrentState(self._network.recurrent_state_size)
        initial_token = self.Token(history=[self._sos_id], state=initial_state)
        tokens[lattice.initial_node.id].append(initial_token)

        sorted_nodes = lattice.sorted_nodes()
        for node in sorted_nodes:
            node_tokens = tokens[node.id]
            assert node_tokens
            if node.id == lattice.final_node.id:
                new_tokens = [self.Token.copy(token) for token in node_tokens]
                self.append_word(new_tokens, self._eos_id)
                return sorted(new_tokens,
                              key=lambda token: token.total_logprob,
                              reverse=True)
            for link in node.out_links:
                new_tokens = [self.Token.copy(token) for token in node_tokens]
                for token in new_tokens:
                    token.ac_logprob += link.ac_logprob
                    token.lat_lm_logprob += link.lm_logprob
                if not link.word.startswith('!'):
                    word_id = self._vocabulary.word_to_id[link.word]
                    self.append_word(new_tokens, word_id)
                tokens[link.end_node.id].extend(new_tokens)

        raise InputError("Could not reach the final node of word lattice.")

    def append_word(self, tokens, target_word_id):
        """Appends a word to each of the given tokens, and updates their scores.

        :type tokens: list of LatticeDecoder.Tokens
        :param tokens: input tokens

        :type target_word_id: int
        :param target_word_id: word ID to be appended to the existing history of
                               each input token
        """

        word_input = [[token.history[-1] for token in tokens]]
        word_input = numpy.asarray(word_input).astype('int64')
        class_input = self._vocabulary.word_id_to_class_id[word_input]
        recurrent_state = [token.state for token in tokens]
        recurrent_state = RecurrentState.combine_sequences(recurrent_state)
        target_class_ids = numpy.ones(shape=(1, len(tokens))).astype('int64')
        target_class_ids *= self._vocabulary.word_id_to_class_id[target_word_id]
        step_result = self.step_function(word_input,
                                         class_input,
                                         *recurrent_state.get(),
                                         target_class_ids)
        output_logprobs = step_result[0]
        output_state = step_result[1:]

        for index, token in enumerate(tokens):
            token.history.append(target_word_id)
            token.state = RecurrentState(self._network.recurrent_state_size)
            # Slice the sequence that corresponds to this token.
            token.state.set([layer_state[:,index:index+1]
                             for layer_state in output_state])
            # The matrix contains only one time step.
            token.nn_lm_logprob += output_logprobs[0,index]
            token.compute_total_logprob(self._weight)
