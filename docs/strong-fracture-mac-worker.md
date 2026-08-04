# Private Mac fracture worker

The externally evaluated SigLIP + MedSigLIP ensemble runs on Mark's Mac GPU and
is reached from the AWS-hosted Fracture Lab without opening any inbound port on
the Mac.

## Privacy and failure behaviour

- The browser sends only the confirmed, de-identified raster previews to
  RadSpeed. DICOM files and their metadata remain local to the browser.
- The website writes the images to a private, encrypted S3 object and sends a
  reference through an encrypted SQS queue.
- The Mac makes outbound HTTPS requests to collect work, writes the result, and
  deletes the input. The website deletes both input and result again after
  collection. A one-day S3 lifecycle rule is the final cleanup backstop.
- The transient bucket is not versioned, so deleting a study does not retain a
  hidden historical version.
- A fresh ready heartbeat is required before the website uploads a study. If the
  Mac is asleep or offline, the strong classifier is marked unavailable and the
  frontier review and other installed models continue.
- Logs contain job state and exception types only, never images, filenames,
  clinical context, accessions, or model results.

## Components

- `deploy/aws/strong_model/local_worker.yml` owns the private bucket, queue,
  dead-letter queue, and separate least-privilege website and Mac identities.
- `llm/strong_fracture_model.py` is the website-side queue client.
- `llm/strong_fracture_worker.py` is the outbound-only background worker.
- `llm/strong_fracture_inference.py` is the exact two-encoder tiled inference
  path used for the public OrthoFrac-XR evaluation.
- `deploy/mac/strong-fracture-worker.sh` and the launch-agent template keep the
  worker running while the Mac is awake and signed in.

The worker wrapper prefers credentials from the current macOS login session and
falls back to macOS Keychain. On this migrated Mac, the login Keychain currently
refuses new items, so the deployed credential is memory-only: it survives sleep
and worker/app restarts but not a full logout or reboot. After a reboot the
website safely marks the strong model offline until the credential is refreshed.
The website credentials belong only in the root-readable production environment
file. Do not place either credential in a repository, shell history,
launch-agent file, diagnostic artifact, or log.
