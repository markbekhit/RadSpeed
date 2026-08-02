# Local text-recognition assets

Fracture Lab bundles these files so image text recognition can run in the
browser without sending the image or recognised text to a separate OCR
service:

- `tesseract.min.js` and `worker.min.js` from Tesseract.js 7.0.0.
- `tesseract-core-lstm.wasm.js` from tesseract.js-core 7.0.0.
- `eng.traineddata.gz` from `@tesseract.js-data/eng` 1.0.0
  (`4.0.0_best_int`).

Tesseract.js and tesseract.js-core are distributed under the Apache License
2.0. Their license texts and the minified-bundle notices are included beside
these files. The English trained-data package is maintained by the Tesseract.js
project and sourced from
<https://www.npmjs.com/package/@tesseract.js-data/eng>.
