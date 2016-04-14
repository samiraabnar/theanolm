#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import OrderedDict
import numpy
from theanolm.exceptions import InputError

class Vocabulary(object):
    """Word or Class Vocabulary

    Vocabulary class provides a mapping between the words and word or class IDs.
    """

    class WordClass(object):
        """Collection of Words and Their Membership Probabilities

        A word class contains one or more words and their probabilities within
        the class. When a class-based model is not wanted, word classes will be
        created with exactly one word per class.

        The class does not enforce the membership probabilities to sum up to
        one. The user has to call ``normalize_probs()`` after creating the
        class.
        """

        def __init__(self, class_id, word_id, prob):
            """Initializes the class with one word with given probability.

            :type class_id: int
            :param class_id: ID for the class

            :type word_id: int
            :param word_id: ID of the initial word in the class

            :type prob: float
            :param prob: the membership probability of the word
            """

            self.id = id
            self.probs = OrderedDict({word_id: prob})

        def add(self, word_id, prob):
            """Adds a word to the class with given probability.

            The membership probabilities are not guaranteed to be normalized.

            :type word_id: int
            :param word_id: ID of the word to add to the class

            :type prob: float
            :param prob: the membership probability of the new word
            """

            self.probs[word_id] = prob

        def get_prob(self, word_id):
            """Returns the class membership probability of a word.

            :type word_id: int
            :param word_id: a word ID that belongs to this class

            :rtype: float
            :returns: the class membership probability of the word
            """

            return self.probs[word_id]

        def normalize_probs(self):
            """Normalizes the class membership probabilities to sum to one.
            """

            prob_sum = sum(self.probs.values())
            for word_id in self.probs:
                self.probs[word_id] /= prob_sum

        def sample(self):
            """Samples a word from the membership probability distribution.

            :rtype: int
            :returns: a random word ID from this class
            """

            word_ids = list(self.probs.keys())
            probs = list(self.probs.values())
            sample_distribution = numpy.random.multinomial(1, probs)
            indices = numpy.flatnonzero(sample_distribution)
            assert len(indices) == 1
            return word_ids[indices[0]]

    def __init__(self, id_to_word, word_to_class_id, word_classes):
        """Creates a vocabulary based on given word-to-class mapping. Prepends
        the vocabulary with special words and updates the word and class IDs.

        :type id_to_word: list
        :param id_to_word: mapping from word IDs to word names

        :type word_to_class_id: dict
        :param word_to_class_id: mapping from words to indices in
                                 ``word_classes``

        :type word_classes: list of WordClass objects
        :param word_classes: list of all the word classes
        """

        self.id_to_word = []
        self._word_classes = []
        self.word_id_to_class_id = []

        if not '<s>' in word_to_class_id:
            word_id = len(self.id_to_word)
            assert word_id == len(self.word_id_to_class_id)
            class_id = len(self._word_classes)
            self.id_to_word.append('<s>')
            self.word_id_to_class_id.append(class_id)
            word_class = Vocabulary.WordClass(class_id, word_id, 1.0)
            self._word_classes.append(word_class)

        if not '</s>' in word_to_class_id:
            word_id = len(self.id_to_word)
            assert word_id == len(self.word_id_to_class_id)
            class_id = len(self._word_classes)
            self.id_to_word.append('</s>')
            self.word_id_to_class_id.append(class_id)
            word_class = Vocabulary.WordClass(class_id, word_id, 1.0)
            self._word_classes.append(word_class)

        if not '<unk>' in word_to_class_id:
            word_id = len(self.id_to_word)
            assert word_id == len(self.word_id_to_class_id)
            class_id = len(self._word_classes)
            self.id_to_word.append('<unk>')
            self.word_id_to_class_id.append(class_id)
            word_class = Vocabulary.WordClass(class_id, word_id, 1.0)
            self._word_classes.append(word_class)

        self.first_normal_word_id = len(self.id_to_word)
        assert self.first_normal_word_id == len(self.word_id_to_class_id)
        self.first_normal_class_id = len(self._word_classes)

        self.id_to_word.extend(id_to_word)
        self.word_to_id = {word: word_id
                           for word_id, word in enumerate(self.id_to_word)}

        for word_id, word in enumerate(id_to_word):
            class_id = self.first_normal_class_id + word_to_class_id[word]
            assert self.first_normal_word_id + word_id == \
                   len(self.word_id_to_class_id)
            self.word_id_to_class_id.append(class_id)

        for word_class in word_classes:
            word_class.probs = {self.first_normal_word_id + word_id: prob
                                for (word_id, prob) in word_class.probs.items()}
            word_class.normalize_probs()
        self._word_classes.extend(word_classes)

    @classmethod
    def from_file(classname, input_file, input_format):
        """Reads vocabulary and possibly word classes from a text file.

        ``input_format`` is one of:
        * "words": ``input_file`` contains one word per line. Each word will be
                   assigned to its own class.
        * "classes": ``input_file`` contains a word followed by whitespace
                     followed by class ID on each line. Each word will be
                     assigned to the specified class. The class IDs can be
                     anything; they will be translated to consecutive numbers
                     after reading the file.
        * "srilm-classes": ``input_file`` contains a class name, membership
                           probability, and word, separated by whitespace, on
                           each line.

        :type input_file: file object
        :param input_file: input vocabulary file

        :type input_format str
        :param input_format: format of the input vocabulary file, "words",
	                     "classes", or "srilm-classes"
        """

        id_to_word = []
        word_to_class_id = dict()
        word_classes = []
        # Mapping from the IDs in the file to our internal class IDs.
        file_id_to_class_id = dict()

        for line in input_file:
            line = line.strip()
            fields = line.split()
            if not fields:
                continue
            if input_format == 'words' and len(fields) == 1:
                word = fields[0]
                file_id = None
                prob = 1.0
            elif input_format == 'classes' and len(fields) == 2:
                word = fields[0]
                file_id = int(fields[1])
                prob = 1.0
            elif input_format == 'srilm-classes' and len(fields) == 3:
                file_id = fields[0]
                prob = float(fields[1])
                word = fields[2]
            else:
                raise InputError("%d fields on one line of vocabulary file: %s" % (len(fields), line))

            word_id = len(id_to_word)
            id_to_word.append(word)

            if word in word_to_class_id:
                raise InputError("Word `%s' appears more than once in the vocabulary file." % word)
            if file_id in file_id_to_class_id:
                class_id = file_id_to_class_id[file_id]
                word_classes[class_id].add(word_id, prob)
            else:
                # No ID in the file or a new ID.
                class_id = len(word_classes)
                word_class = Vocabulary.WordClass(class_id, word_id, prob)
                word_classes.append(word_class)
                if not file_id is None:
                    file_id_to_class_id[file_id] = class_id
            word_to_class_id[word] = class_id

        return classname(id_to_word, word_to_class_id, word_classes)

    @classmethod
    def from_word_counts(classname, word_counts, num_classes=None):
        """Creates a vocabulary and dummy classes from word counts.

        :type word_counts: dict
        :param word_counts: dictionary from words to the number of occurrences
                            in the corpus

        :type num_classes: int
        :param num_classes: number of classes to create in addition to the
                            special classes, or None for one class per word
        """

        id_to_word = []
        word_to_class_id = dict()
        word_classes = []

        if num_classes is None:
            num_classes = len(word_counts)

        class_id = 0
        for word, _ in sorted(word_counts.items(),
                              key=lambda x: x[1]):
            word_id = len(id_to_word)
            id_to_word.append(word)

            if class_id < len(word_classes):
                word_classes[class_id].add(word_id, 1.0)
            else:
                assert class_id == len(word_classes)
                word_class = Vocabulary.WordClass(class_id, word_id, 1.0)
                word_classes.append(word_class)
            word_to_class_id[word] = class_id
            class_id = (class_id + 1) % num_classes

        return classname(id_to_word, word_to_class_id, word_classes)

    @classmethod
    def from_corpus(classname, input_files, num_classes=None):
        """Creates a vocabulary based on word counts from training set.

        :type input_files: list of file or mmap objects
        :param input_files: input text files

        :type num_classes: int
        :param num_classes: number of classes to create in addition to the
                            special classes, or None for one class per word
        """

        word_counts = dict()

        for subset_file in input_files:
            for line in subset_file:
                for word in line.split():
                    if not word in word_counts:
                        word_counts[word] = 1
                    else:
                        word_counts[word] += 1

        return classname.from_word_counts(word_counts, num_classes)

    def num_words(self):
        """Returns the number of words in the vocabulary.

        :rtype: int
        :returns: the number of words in the vocabulary
        """

        return len(self.id_to_word)

    def num_classes(self):
        """Returns the number of word classes.

        :rtype: int
        :returns: the number of words classes
        """

        return len(self._word_classes)

    def word_to_class_id(self, word):
        """Returns the class ID of given word.

        :type word: str
        :param word: a word

        :rtype: int
        :returns: ID of the class where ``word`` is assigned to
        """

        return self.word_id_to_class_id[self.word_to_id[word]]

    def words_to_ids(self, words):
        """Translates words into word IDs.

        :type words: list of strs
        :param words: a list of words

        :rtype: list of ints
        :returns: the given words translated into word IDs
        """

        unk_id = self.word_to_id['<unk>']
        return [self.word_to_id[word]
                if word in self.word_to_id
                else unk_id
                for word in words]

    def class_id_to_word_id(self, class_id):
        """Samples a word from the membership probability distribution of a
        class. (If classes are not used, returns the one word in the class.)

        :type class_id: int
        :param class_id: a class ID

        :rtype: int
        :returns: a word from the given class
        """

        return self._word_classes[class_id].sample()

    def word_ids_to_classes(self, word_ids):
        """Translates word IDs into class names. If a class
        contains only one word, class name will be the word. Otherwise class
        name will be CLASS-12345, where 12345 is the internal class ID.

        :type word_ids: list of ints
        :param word_ids: a list of word IDs

        :rtype: list of strings
        :returns: class names of the given word IDs
        """

        return [self._class_name(self._word_classes[word_id])
                for word_id in word_ids]

    def _class_name(self, word_class):
        """If given class contains only one word, returns the word. Otherwicse
        returns CLASS-12345, where 12345 is the internal class ID.

        :type word_class: WordClass
        :param word_class: a word class object

        :rtype: str
        :returns: a name for the class
        """

        if len(word_class.probs) == 1:
            word_id = next(iter(word_class.probs))
            return self.id_to_word[word_id]
        elif word_class.id is None:
            return 'CLASS'
        else:
            return 'CLASS-{0:05d}'.format(word_class.id)

    def get_word_prob(self, word_id):
        """Returns the class membership probability of a word.

        :type word_id: int
        :param word_id: ID of a word

        :rtype: float
        :returns: the probability of the word within its class
        """

        class_id = self.word_id_to_class_id[word_id]
        word_class = self._word_classes[class_id]
        return word_class.get_prob(word_id)

    def words(self):
        """A generator for all the words in the vocabulary.

        :rtype: generator of str
        :returns: iterates through the words
        """

        for word in self.word_to_id.keys():
            yield word

    def __contains__(self, word):
        """Tests if ``word`` is included in the vocabulary.

        :type word: str
        :param word: a word

        :rtype: bool
        :returns: True if ``word`` is in the vocabulary, False otherwise.
        """

        return word in self.word_to_id