import numpy as np
from sklearn.cross_validation import train_test_split

from brainpy.eeg import EEG

from utils import one_hot_encoder
from matlab_data_reader import matlab_data_reader


class SimpleDataset(object):
    def __init__(self, name, x_train, x_test, y_train, y_test):
        self.name = name
        self.x_train = x_train
        self.x_test = x_test
        self.y_train = y_train
        self.y_test = y_test


def train_test_dataset(data, labels, test_proportion, dataset_name="no_name", random_seed=42):
    x_train, x_test, y_train, y_test = train_test_split(data.squeeze(), np.asarray(labels, dtype=np.int32),
                                                        test_size=test_proportion, random_state=random_seed)
    return SimpleDataset(dataset_name, x_train, x_test, y_train, y_test)


class EEGDataSetBatch(object):
    def __init__(self, data, labels):
        self._cycles_completed = 0
        self._index_in_cycle = 0
        self._data = data
        self._labels = labels
        self._n_class = len(labels[0])

    @property
    def data(self):
        return self._data

    @property
    def labels(self):
        return self._labels

    @property
    def n_trials(self):
        return self._data.shape[0]

    @property
    def n_channels(self):
        return self._data.shape[1]

    @property
    def trial_size(self):
        return self._data.shape[2]

    @property
    def n_comps(self):
        if self._data.ndim == 4:
            return self._data.shape[3]
        return 1

    @property
    def n_class(self):
        return self._n_class

    @property
    def cycles_completed(self):
        return self._cycles_completed

    def next_batch(self, batch_size):
        """Return the next `batch_size` examples from this data set."""
        start = self._index_in_cycle
        self._index_in_cycle += batch_size
        if self._index_in_cycle > self.n_trials:
            # Finished epoch
            self._cycles_completed += 1
            # Shuffle the data
            perm = np.arange(self.n_trials)
            np.random.shuffle(perm)
            self._data = self._data[perm]
            self._labels = self._labels[perm]
            # Start next epoch
            start = 0
            self._index_in_cycle = batch_size
            assert batch_size <= self.n_trials
        end = self._index_in_cycle
        return self._data[start:end], self._labels[start:end]


# TODO: RESHAPE DATA FOR POTENTIAL AND LAPLACIAN
def build_data_sets(file_name, name="no_name", avg_group_size=None, derivation=None, random_state=42, test_proportion=0.2):
    eeg = EEG(data_reader=matlab_data_reader).read(file_name)
    n_channels = eeg.n_channels
    if avg_group_size:
        eeg.average_trials(avg_group_size, inplace=True)
    derivation = derivation or 'potential'
    if derivation.lower() == "electric_field":
        eeg.get_electric_field(inplace=True)
        eeg.data = eeg.data.reshape(eeg.n_channels, eeg.trial_size, -1, 3).transpose((2, 0, 1, 3))
    elif derivation.lower() == 'laplacian':
        eeg.get_laplacian(inplace=True)
    n_classes = len(np.unique(eeg.trial_labels))
    labels = one_hot_encoder(eeg.trial_labels)
    X_train, X_test, y_train, y_test = train_test_split(eeg.data, labels, test_size=test_proportion,
                                                        random_state=random_state)
    return type('DataSet', (), {'train': EEGDataSetBatch(X_train, y_train),
                                'test': type('Dataset', (), {'samples': X_test, 'labels': y_test}),
                                'trial_size': eeg.trial_size, 'name': name, 'derivation': derivation,
                                'avg_group_size': avg_group_size, 'random_state': random_state,
                                'test_proportion': test_proportion, 'n_channels': n_channels,
                                'n_comps': eeg.n_comps, 'n_classes': n_classes})
