# data/

Unzip the sample pack here so it looks like this:

    data/sample_pack/
      README.md
      schema.json
      labelled/     L01.pdf L01.json   L02.jpg L02.json   ...   L10.pdf L10.json
      unlabelled/   U01.pdf  U02.jpg  ...  U10.pdf

Labels are matched to documents by name (L01.pdf with L01.json). Use --labels PATH if they live somewhere else. Everything in this folder
except this file is git-ignored, because the assignment says not to publish the sample documents.

`python scripts/stress.py` writes data/stress/ (damaged copies of the labelled documents) for the robustness test.
