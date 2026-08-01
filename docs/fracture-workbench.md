# Fracture Lab

Fracture Lab is an authenticated RadSpeed page for reviewing the experimental
fracture benchmark. It is available at `/fracture-workbench` to any user who
has completed the existing RadSpeed sign-in.

## Current scope

- 1,132 eligible radiographs from the public
  [OrthoFrac-XR v1](https://doi.org/10.6084/m9.figshare.32021085.v1) research
  dataset by Tabib, Liza, Bijoy, Hasan and Khan, licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Dataset labels, the hybrid router's calibrated estimate, component model
  scores, frontier-model comments, and approximate proposed boxes.
- Filters for all cases, any model error, and cases all models classified
  correctly.

This is a retrospective benchmark viewer, not live clinical inference. Patient
uploads are deliberately not enabled. It must not be used as a medical device
or as the sole basis for patient care.

The benchmark HTML is stored outside the public static directory and both the
page and each image route use the standard RadSpeed authentication dependency.
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
