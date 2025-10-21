Workflow managing CBRAIN Processing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following diagram highlights how the "update_processing" function manages which subjects/sessions
are selected for processing for a specific tool within CBRAIN. If you are not a member of the HBCD Data
Cordinating Center, this diagram likely is not important for you.

The "update_processing" command found in the `HBCD_CBRAIN_PROCESSING repository <https://github.com/erikglee/HBCD_CBRAIN_PROCESSING>`_
will update processing for a given pipeline in CBRAIN. By "update processing" we mean that the S3 bucket
where all the BIDS data is stored will be queried to determine if any new processing should occur.

The current diagram is designed to describe the state of processing workflows as of October 21, 2025.

.. image:: ./images/CBRAIN_Proc_Workflow.drawio.svg