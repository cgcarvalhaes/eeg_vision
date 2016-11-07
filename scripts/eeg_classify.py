import argparse

from brainpy.eeg import EEG

import settings
from base.classification_manager import ClassificationManager
from classifiers.anova_lda_classifier import AnovaLDAClassifier
from classifiers.anova_svm_classifier import AnovaSVMClassifier
from classifiers.lda_classifier import LDAClassifier
from etc.data_reader import data_reader


# TODO: DEBUG FOR THE POTENTIAL
# TODO: CLASSIFICATION RATES SEEM TO DISAGREE WITH PREVIOUS RESULTS
# TODO: IMPLEMENT AN OPTION FOR VERBOSITY ON THE CLASSIFICATION MANAGER
# TODO: SAVE DATA ON MONGODB
# TODO: SAVE MODEL ON MONGODB
# TODO: WORK ON TENSOR FLOW
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--subject", choices=settings.SUBJECTS, default=settings.SUBJECTS[0])
    parser.add_argument("-g", "--group_size", type=int, default=1)
    parser.add_argument("-t", "--test_proportion", type=float, default=0.2)
    parser.add_argument("-r", "--random_seed", type=int, default=42)
    parser.add_argument("-c", "--channel_scheme", choices=['single', 'multi'], default='single')
    args = parser.parse_args()

    file_name = settings.MAT_FILES[args.subject]
    eeg = EEG(data_reader=data_reader).read(file_name)
    eeg.average_trials(args.group_size, inplace=True)
    # eeg.get_electric_field(inplace=True)

    clf = ClassificationManager([LDAClassifier(), AnovaLDAClassifier()], test_proportion=args.test_proportion,
                                random_seed=args.random_seed, channel_scheme=args.channel_scheme)
    clf.eval(eeg)

    print "Complete."
