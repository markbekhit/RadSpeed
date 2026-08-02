# Fracture Lab

Fracture Lab is an authenticated RadSpeed page for reviewing the experimental
fracture benchmark. It is available at `/fracture-workbench` to any user who
has completed the existing RadSpeed sign-in.

It also accepts one to four PNG, JPEG or WebP radiograph screenshots from a
single study for an ephemeral live review. Before upload, the browser runs the
bundled text-recognition engine locally, blacks out detected text other than
standard laterality/view markers, and shows the exact cleaned copy that will be
sent. The user can drag over anything missed and must confirm the previews
before the analysis route accepts the upload. The original file and filename
are never submitted. RadSpeed then validates and re-encodes the cleaned raster
to remove EXIF/embedded metadata, sends it to the configured vision-model
provider, and does not write the file to its persistent volume. A second visual
pass challenges the first assessment before the result is returned.

Automatic text recognition is a safety aid rather than a guarantee. Analysis
remains fail-closed behind the final preview confirmation, and users should
remove an image or manually cover any ambiguous area. The OCR runtime, English
language data and image processing are served by RadSpeed and execute in the
browser; no image or recognised text is sent to an OCR service.

## Current scope

- 1,132 eligible radiographs from the public
  [OrthoFrac-XR v1](https://doi.org/10.6084/m9.figshare.32021085.v1) research
  dataset by Tabib, Liza, Bijoy, Hasan and Khan, licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Dataset labels, the hybrid router's calibrated estimate, component model
  scores, frontier-model comments, and approximate proposed boxes.
- Filters for all cases, any model error, and cases all models classified
  correctly.

The live result uses cautious four-state terminology, an explicitly
uncalibrated model-confidence percentage and up to three suggested regions per
view. It is experimental decision support, not a medical device, and must not
be used as the sole basis for patient care. Direct DICOM ingestion and the open
detector/classifier are not yet hosted; the current live route is frontier
multi-view review plus a frontier visual critic.

The benchmark HTML is stored outside the public static directory and both the
page, live-analysis route and each benchmark image route use the standard
RadSpeed authentication dependency.
Production images live on the persistent Fly volume under
`/data/fracture_workbench/images` and are not included in the Git repository.
`RADSPEED_FRACTURE_WORKBENCH_DIR` can override the data root for local tests.

## Rebuilding the viewer

The checked-in page is generated from the benchmark repository's offline HTML:

```bash
python tools/build_fracture_workbench.py \
  ../xray-fracture-benchmark/results/hybrid/orthofrac_xr_review.html \
  web/private/fracture_workbench.html
```

The build fails if it cannot find and convert the expected source image paths.
