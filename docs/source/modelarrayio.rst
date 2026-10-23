ModelArrayIO
============

ModelArrayIO is a Python package for converting neuroimaging data between formats
such as CIFTI, NIfTI, and MRtrix ``.mif`` and the HDF5 format used by the
`ModelArray <https://pennlinc.github.io/ModelArray/>`_ R package. It can also
export ModelArray statistical results back to neuroimaging formats.

For installation instructions, usage examples, and complete documentation, see
the `ModelArrayIO documentation <https://modelarrayio.readthedocs.io/en/latest/>`_.

qsirecon-ModelArrayIO
---------------------

For HBCD diffusion data, ModelArrayIO is used as a downstream aggregation step,
converting subject-level MRI scalar maps from QSIRecon reconstruction methods
into cohort-level arrays. This enables large-scale statistical analyses with
ModelArray without loading individual subject files.

The outputs include scalar maps from:

* DIPYDKI
* DSI Studio
* TORTOISE model-tensor
* TORTOISE MAPMRI

Processing
^^^^^^^^^^

ModelArrayIO reads input file paths from the cohort CSV using
``SCALAR_COLUMNS``. The input modality is detected from the source file
extension. Data are stored as ``float32`` using the HDF5 backend with gzip
compression at level 9. HDF5 spatial chunks are sized to approximately 32 MiB,
and four parallel workers are used when loading input files from S3.

Each ``.h5`` output is paired with a ``.csv`` file indexing the subjects and
sessions included in that array.

See the `HBCD dMRI processing documentation
<https://github.com/nbdc-datahub/hbcd-docs/blob/3.0-READMEs/docs/instruments/mri/dmri.md#processing>`_
for additional context.

ModelArrayIO run command
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

   modelarrayio to-modelarray \
       --cohort-file ${cohort_csv} \
       --output ${out_h5} \
       --scalar-columns ${SCALAR_COLUMNS} \
       --backend hdf5 \
       --dtype float32 \
       --compression gzip \
       --compression-level 9 \
       --s3-workers 4 \
       --log-level INFO \
       --target-chunk-mb 32

Outputs
^^^^^^^

.. code-block:: text

   hbcd/
   └── derivatives/
       └── qsirecon-ModelArrayIO/
           # DIPYDKI outputs
           ├── qsirecon-DIPYDKI_space-{SPACE}_model-{tensor|dki}_param-{PARAM}.h5
           ├── qsirecon-DIPYDKI_space-{SPACE}_model-{tensor|dki}_param-{PARAM}.csv
           # DSI Studio outputs
           ├── qsirecon-DSIStudio_space-{SPACE}_model-{tensor|gqi|rdi}_param-{PARAM}.h5
           ├── qsirecon-DSIStudio_space-{SPACE}_model-{tensor|gqi|rdi}_param-{PARAM}.csv
           # TORTOISE model-tensor outputs
           ├── qsirecon-TORTOISE_model-tensor_space-{SPACE}_param-{PARAM}.h5
           ├── qsirecon-TORTOISE_model-tensor_space-{SPACE}_param-{PARAM}.csv
           # TORTOISE MAPMRI outputs
           ├── qsirecon-TORTOISE_model-MAPMRI_space-{SPACE}_param-{PARAM}.h5
           └── qsirecon-TORTOISE_model-MAPMRI_space-{SPACE}_param-{PARAM}.csv

``PARAM`` identifies a QSIRecon scalar map or parameter. ``SPACE`` can be
``MNIInfant+1``, ``MNIInfant+3``, ``MNIInfant+5``, or ``MNIInfant+7``.

The scalar parameters included in these outputs are:

.. list-table::
   :header-rows: 1

   * - Reconstruction method
     - Parameters
   * - DIPY DKI
     - ``fa`` (fractional anisotropy), ``ad`` (axial diffusivity), ``rd`` (radial diffusivity), ``md`` (mean diffusivity), ``ak`` (axial kurtosis), ``mk`` (mean kurtosis), ``mkt`` (mean kurtosis tensor), ``rk`` (radial kurtosis), ``kfa`` (kurtosis fractional anisotropy)
   * - DSI Studio
     - ``fa`` (fractional anisotropy), ``ad`` (axial diffusivity), ``rd`` (radial diffusivity), ``md`` (mean diffusivity), ``ha`` (helix angle), ``gfa`` (generalized fractional anisotropy), ``qa`` (quantitative anisotropy), ``iso`` (isotropic diffusion), ``rd1`` and ``rd2`` (restricted diffusion indices 1 and 2)
   * - TORTOISE model-tensor
     - ``fa`` (fractional anisotropy), ``ad`` (axial diffusivity), ``rd`` (radial diffusivity), ``am`` (axial mean diffusivity), ``li`` (linearity index)
   * - TORTOISE MAPMRI
     - ``ng`` (non-Gaussianity), ``ngpar`` (parallel non-Gaussianity), ``ngperp`` (perpendicular non-Gaussianity), ``pa`` (propagator anisotropy), ``path`` (thresholded propagator anisotropy), ``rtap`` (return-to-axis probability), ``rtop`` (return-to-origin probability), ``rtpp`` (return-to-plane probability)

xcp_d-HASH-ModelArrayIO
-----------------------

For HBCD, ModelArrayIO is used as a downstream aggregation step to convert
subject-level XCP-D outputs into cohort-level arrays. This enables large-scale
statistical analyses without loading individual subject files.

The outputs include cohort-level HDF5 arrays for:

* Surface morphometry (curvature, sulcal depth, and cortical thickness)
* Functional maps (ALFF and ReHo)
* Resting-state functional connectivity

Processing
^^^^^^^^^^

ModelArrayIO reads input file paths from the cohort CSV using
``SCALAR_COLUMNS``. Input modalities are detected from the source file
extensions. Data are stored as ``float32`` using the HDF5 backend with gzip
compression at level 9. HDF5 spatial chunks are sized to approximately 32 MiB,
and four parallel workers are used for S3-based input files.

Each ``.h5`` output is paired with a ``.csv`` file indexing the included
subjects and sessions.

See the `HBCD fMRI processing documentation
<https://github.com/nbdc-datahub/hbcd-docs/blob/3.0-READMEs/docs/instruments/mri/fmri.md#processing>`_
and `ModelArrayIO usage documentation
<https://modelarrayio.readthedocs.io/en/latest/usage.html>`_ for additional
details.

ModelArrayIO run command and parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

   modelarrayio to-modelarray \
       --cohort-file ${cohort_csv} \
       --output ${out_h5} \
       --scalar-columns ${SCALAR_COLUMNS} \
       --backend hdf5 \
       --dtype float32 \
       --compression gzip \
       --compression-level 9 \
       --s3-workers 4 \
       --log-level INFO \
       --target-chunk-mb 32

Outputs
^^^^^^^

.. code-block:: text

   hbcd/
   └── derivatives/
       └── xcp_d-{HASH}-ModelArrayIO/
           # Surface morphometry
           ├── xcp_d-{HASH}_param-{curv|sulc|thickness}.h5
           ├── xcp_d-{HASH}_param-{curv|sulc|thickness}.csv
           # Functional maps
           ├── xcp_d-{HASH}_param-{alff|reho}.h5
           ├── xcp_d-{HASH}_param-{alff|reho}.csv
           # Resting-state functional connectivity
           ├── xcp_d-{HASH}_task-rest_seg-{ATLAS}_param-pearsoncorrelation.h5
           └── xcp_d-{HASH}_task-rest_seg-{ATLAS}_param-pearsoncorrelation.csv

``HASH`` is ``d902942d+7a4c379b`` or ``364caa63+7a4c379b``. 
``ATLAS`` can be
``4S-{156|256|...|1056}Parcels``, ``Glasser``, ``Gordon``, ``MIDB``, or
``MyersLabonte``.
