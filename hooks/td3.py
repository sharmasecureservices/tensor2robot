# coding=utf-8
# Copyright 2019 The Tensor2Robot Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Hook builders for TD3 distributed training with SavedModels."""

from __future__ import absolute_import
from __future__ import division

from __future__ import print_function

import gin
from tensor2robot.export_generators import abstract_export_generator
from tensor2robot.hooks import checkpoint_hooks
from tensor2robot.hooks import hook_builder
from tensor2robot.models import model_interface
import tensorflow as tf  # tf

from typing import Text, List


@gin.configurable
class TD3Hooks(hook_builder.HookBuilder):
  """Creates hooks for exporting models for serving in TD3 distributed training.

  See:
    "Addressing Function Approximation Error in Actor-Critic Methods"
    by Fujimoto et al.

   https://arxiv.org/abs/1802.09477

  These hooks manage exporting of SavedModels to two different directories:
  `export_dir` contains the latest version of the model, `lagged_export_dir`
  contains a lagged version, delayed by one interval of `save_secs`.

  Arguments:
    export_dir: Directory to output the latest models.
    lagged_export_dir: Directory containing a lagged version of SavedModels
    save_secs: Interval to save models, and copy the latest model from
      `export_dir` to `lagged_export_dir`.
    num_versions: Number of model versions to save in each directory
    use_preprocessed_features: Whether to export SavedModels which do *not*
      incldue preprocessing. This is useful for offloading the preprocessing
      graph to the client.
  """

  def __init__(
      self,
      export_dir,
      lagged_export_dir,
      batch_sizes_for_export,
      save_secs = 90,
      num_versions = 3,
      use_preprocessed_features=False,
  ):
    super(TD3Hooks, self).__init__()
    self._save_secs = save_secs
    self._num_versions = num_versions
    self._export_dir = export_dir
    self._lagged_export_dir = lagged_export_dir
    self._use_preprocessed_features = use_preprocessed_features
    self._batch_sizes_for_export = batch_sizes_for_export

  def create_hooks(
      self, t2r_model, estimator,
      export_generator
  ):
    export_generator.set_specification_from_model(t2r_model)
    warmup_requests_file = export_generator.create_warmup_requests_numpy(
        batch_sizes=self._batch_sizes_for_export,
        export_dir=estimator.model_dir)

    def _export_fn(export_dir):
      res = estimator.export_saved_model(
          export_dir_base=export_dir,
          serving_input_receiver_fn=export_generator
          .create_serving_input_receiver_numpy_fn(),
          assets_extra={'tf_serving_warmup_requests': warmup_requests_file})
      return res

    return [
        tf.contrib.tpu.AsyncCheckpointSaverHook(
            save_secs=self._save_secs,
            checkpoint_dir=estimator.model_dir,
            listeners=[
                checkpoint_hooks.LaggedCheckpointListener(
                    export_fn=_export_fn,
                    num_versions=self._num_versions,
                    export_dir=self._export_dir,
                    lagged_export_dir=self._lagged_export_dir)
            ])
    ]
