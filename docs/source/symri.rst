SyMRI relaxometry workflow
==========================

The HBCD SyMRI relaxometry workflow processes QALAS MRI scans to produce
quantitative relaxometry maps and synthetic weighted images. It downloads DICOM
archives and their quality-control (QC) metadata from an S3 bucket, runs the
SyMRI container on a selected QALAS scan, converts the resulting DICOMs to
BIDS-formatted derivatives with ``dcm2bids``, and uploads the derivatives to
the configured S3 destination.

The workflow is maintained in the
`HBCD SyMRI relaxometry workflow repository
<https://github.com/DCAN-Labs/hbcd_symri_relaxometry_workflow>`_. SyMRI methods
for estimating quantitative maps from QALAS scans are described in
`this publication <https://doi.org/10.1016/j.mri.2019.08.031>`_.

Processing workflow
-------------------

For each subject and session, the workflow:

#. Finds DICOM QC JSON files ending in ``_mripcqc_info.json`` and groups them
   by subject and session.
#. Selects the best QALAS scan using QC metadata. Only scans with ``QC == 1``
   are eligible. The selection prefers lower ``QU_motion``, then lower
   ``aqc_motion``, then higher ``brain_SNR``. If ``QU_motion`` is unavailable,
   it compares ``aqc_motion`` and ``brain_SNR`` instead.
#. Downloads and unpacks the archive containing the selected QALAS scan.
#. Runs the SyMRI Singularity container to generate quantitative maps and
   synthetic-weighted-image DICOMs.
#. Converts the output DICOMs to BIDS derivatives with ``dcm2bids``, adds
   provenance and QC details to JSON sidecars, and saves the SyMRI container
   log alongside the images.
#. Uploads the BIDS derivatives to the configured S3 bucket.

When multiple candidates are available, required QC values must be present for
the comparison; scans with incomplete QC information may be deferred. The
workflow tracks processed sessions and possible reprocessing needs in local
JSON logs.

Outputs
-------

By default, the workflow produces the following files under the session's
``anat`` directory:

* ``*_acq-QALAS_T1map.nii.gz`` and JSON sidecar: quantitative T1 map, in ms.
* ``*_acq-QALAS_T2map.nii.gz`` and JSON sidecar: quantitative T2 map, in ms.
* ``*_acq-QALAS_PDmap.nii.gz`` and JSON sidecar: proton-density map.
* ``*_acq-QALAS_TB1map.nii.gz`` and JSON sidecar: B1 transmit-field map.
* ``*_acq-QALAS_T1w.nii.gz`` and JSON sidecar: synthetic T1-weighted image.
* ``*_acq-QALAS_T2w.nii.gz`` and JSON sidecar: synthetic T2-weighted image.
* ``sub-<subject>_ses-<session>_acq-QALAS_desc-SymriContainer.log``: SyMRI
  container log.

The local BIDS directory is organized as:

.. code-block:: text

   sub-<subject>/
   └── ses-<session>/
       └── anat/
           ├── sub-<subject>_ses-<session>_acq-QALAS_T1map.nii.gz
           ├── sub-<subject>_ses-<session>_acq-QALAS_T1map.json
           └── ...

The default S3 upload prefix is ``reid_derivatives/symri/`` within the
configured output bucket, followed by the ``sub-<subject>/ses-<session>/anat``
directory. Use ``--no_upload`` to leave results in the local working directory
instead. Each map and synthetic-image type can also be omitted with its
corresponding ``--exclude_*`` option.

JSON sidecars are enriched with source ``SeriesInstanceUID`` and
``StudyInstanceUID``, ``QU_motion`` and ``aqc_motion`` values, and derivative
provenance. T1 and T2 map sidecars specify units of milliseconds. Synthetic
image sidecars include the synthetic image type and its generation parameters.

Running the workflow
--------------------

The workflow requires Python 3.9, the dependencies in its ``environment.yml``,
Singularity, ``dcm2bids``, a licensed SyMRI container, and separate S3
configuration files for the input DICOM bucket and output derivatives bucket.
Each S3 configuration file provides ``access_key``, ``secret_key``, and
``host_base`` settings.

The command takes paths to the two S3 configuration files, the SyMRI container,
and a local processing directory:

.. code-block:: console

   python HBCD_SYMRI_RELAXOMETRY_WORKFLOW/update.py \
       <dicom_config_path> \
       <bids_config_path> \
       <symri_container_path> \
       <base_directory_for_proc> \
       --custom_processing_batch_size 20

The default batch size is 20 subject/session pairs. Optional arguments can
select alternate SyMRI layout, global, or ``dcm2bids`` configuration files;
set the DICOM prefix or bucket names; choose a custom working directory; retain
intermediate files; or exclude selected output types. ``--no_upload`` skips
S3 upload and retains local results.

Tracking and reprocessing
-------------------------

The workflow stores timestamped ``tracking_log_*.json`` files under
``<base_directory_for_proc>/logs`` to record processed sessions. The
``reproc_log.json`` file in the base directory tracks sessions that may need
attention, including sessions with a new archive, a missing archive, no
generated NIfTIs, incomplete QC/archive information, or a known early Philips
protocol issue.

To explicitly rerun a session, add its subject/session key to the
``to_reprocess`` list in ``reproc_log.json`` and run the workflow again.
Reprocessing may overwrite previously uploaded derivatives for that session.
