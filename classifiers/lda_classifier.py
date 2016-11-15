from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.pipeline import Pipeline

from classifiers.base_classifier import BaseClassifier
from classifiers.merge_components import MergeComponents


class LDAClassifier(BaseClassifier):
    @property
    def sklearn_classifier(self):
        return LinearDiscriminantAnalysis()

    @property
    def pipeline(self):
        return Pipeline([('merge_comps', MergeComponents()), ('classifier', self.sklearn_classifier)])
