import json
import numpy as np
import os

from ml_hyperparam import Type
from ml_block import MLBlock


class MLPipeline(object):
    """A pipeline that the DeepMining system can operate on.

    Attributes:
        steps_dict: A dictionary mapping this pipeline's step names to
            DMSteps.
    """

    def __init__(self, steps, dataflow=None):
        """Initializes a DmPipeline with a list of corresponding
        DmSteps.

        Args:
            steps: A list of DmSteps composing this pipeline.
        """
        # Contains the actual primitives.
        self.steps_dict = {
            k: v
            for (k, v) in [(step.name, step) for step in steps]
        }

        # For now, just use a list to order the steps.
        self.dataflow = dataflow if dataflow is not None else [
            step.name for step in steps
        ]

    @classmethod
    def from_json_metadata(cls, json_metadata):
        """Initializes a DmPipeline with a list of JSON metadata
        defining DmSteps.

        Args:
            json_metadata: A list of JSON objects representing the
                DmSteps composing this pipeline.

        Returns:
            A DmPipeline defined by the JSON steps.
        """
        return cls([MLBlock.from_json(json_md) for json_md in json_metadata])

    @classmethod
    def from_json_filepaths(cls, json_filepath_list):
        """Initializes a DmPipeline with a list of paths to JSON files
        defining DmSteps.

        Args:
            json_filepath_list: A list of paths to JSON files
                representing the DmSteps composing this pipeline.

        Returns:
            A DmPipeline defined by the JSON files.
        """
        loaded_json_metadata = [
            json.load(open(json_filepath))
            for json_filepath in json_filepath_list
        ]
        return cls.from_json_metadata(loaded_json_metadata)

    @classmethod
    def from_dm_json(cls, json_names):
        """Initializes a DmPipeline with a list of step names.

        These step names should correspond to the JSON file names
        present in the components/primitive_jsons directory.

        Args:
            json_names: A list of primitive names corresponding to
                JSON files in components/primitive_jsons.

        Returns:
            A DmPipeline defined by the JSON primitive names.
        """
        current_dir = os.path.dirname(os.path.realpath(__file__))
        json_dir = os.path.join(current_dir, '../components/primitive_jsons')

        json_filepaths = []
        for json_name in json_names:
            path_to_json = os.path.join(json_dir, '%s.%s' % (json_name,
                                                             'json'))
            if not os.path.isfile(path_to_json):
                raise ValueError(
                    "No JSON corresponding to the specified name (%s) exists."
                    % json_name)
            json_filepaths.append(path_to_json)

        return cls.from_json_filepaths(json_filepaths)

    def update_hyperparams(self, hyperparams):
        """Updates the specified hyperparameters of this pipeline.

        Unspecified hyperparameters are not affected.

        Args:
            hyperparams: A list of Hyperparameters to update.
        """
        for hyperparam in hyperparams:
            step_name = hyperparam.step_name

            self.steps_dict[step_name].tunable_hyperparams[
                hyperparam.param_name] = hyperparam
            self.steps_dict[step_name].build_model()

    def get_tunable_hyperparams(self):
        """Gets all tunable hyperparameters belonging to this pipeline.

        Returns:
            A list of tunable hyperparameters belonging to this
            pipeline.
        """
        tunable_hyperparams = []
        for step in self.steps_dict.values():
            tunable_hyperparams += list(step.tunable_hyperparams.values())
        return tunable_hyperparams

    def get_hyperparam_vec(self):
        """Gets all tunable hyperparameter values of this pipeline.

        The values are ordered corresponding to the order of
        hyperparameters in the list returned by the
        get_tunable_hyperparams() method.

        Returns:
            A numpy array of hyperparameter values of this pipeline.
            A value in index i of this array corresponds to the
            hyperparameter in index i of the list returned by
            get_tunable_hyperparams().
        """
        all_tunable_hyperparams = self.get_tunable_hyperparams()
        return np.array(
            [hyperparam.value for hyperparam in all_tunable_hyperparams])

    def set_from_hyperparam_vec(self, hyperparam_vec):
        """Sets the hyperparameters of this pipeline given a list of values.

        The list of values contains a value for each hyperparameter. The
        values must be ordered corresponding to the order of
        hyperparameters in the list returned by the
        get_tunable_hyperparams() method.

        Args:
            hyperparam_vec: A numpy array containing values for each
                hyperparameter. A value in index i of this array
                corresponds to the hyperparameter in index i of the list
                returned by get_tunable_hyperparams().
        """
        all_tunable_hyperparams = self.get_tunable_hyperparams()
        for i in range(len(hyperparam_vec)):
            new_val = hyperparam_vec[i]
            if (all_tunable_hyperparams[i].param_type == Type.INT
                    or all_tunable_hyperparams[i].param_type == Type.INT_EXP):
                new_val = int(new_val)
            all_tunable_hyperparams[i].value = new_val
        self.update_hyperparams(all_tunable_hyperparams)

    def fit(self, x, y):
        """Fits this pipeline to the specified training data.

        Args:
            x: Training data. Must fulfill input requirements of the
                first step of the pipeline.
            y: Training targets. Must fulfill label requirements for
                all steps of the pipeline.
        """
        # Initially our transformed data is simply our input data.
        transformed_data = x
        for step_name in self.dataflow:
            step = self.steps_dict[step_name]

            hyperparam_kwargs = {
                name: step.tunable_hyperparams[name].value
                for name in step.tunable_hyperparams
            }
            step.step_instance = step.step_model(**hyperparam_kwargs)

            getattr(step.step_instance, step.fit_func)(transformed_data, y)
            transformed_data = getattr(step.step_instance,
                                       step.produce_func)(transformed_data)

    def predict(self, x):
        """Makes predictions with this pipeline on the specified input
        data.

        fit() must be called at least once before predict().

        Args:
            x: Input data. Must fulfill input requirements of the first
                step of the pipeline.

        Returns:
            The predicted values.
        """
        transformed_data = x
        for step_name in self.dataflow:
            step = self.steps_dict[step_name]
            if step.step_instance is None:
                raise AttributeError(
                    "fit() must be called at least once before predict().")
            transformed_data = getattr(step.step_instance,
                                       step.produce_func)(transformed_data)

        # The last value stored in transformed_data is our final output value.
        return transformed_data

    def __str__(self):
        return str(self.to_dict())

    def to_dict(self):
        all_tunable_hyperparams = self.get_tunable_hyperparams()
        return {
            '{0}__{1}'.format(hyperparam.step_name, hyperparam.param_name):
            hyperparam.value
            for hyperparam in all_tunable_hyperparams
        }