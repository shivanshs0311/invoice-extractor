| Configuration | Docs fully correct | Field accuracy | Avg cost / doc | Run cost | Docs retried |
| --- | ---: | ---: | ---: | ---: | ---: |
| cascade: text/vision first, strong model on failure (default) | 10/10 | 100% | $0.00165 | $0.01649 | 0/10 |
| text layer only, cheap model | 10/10 | 100% | $0.00165 | $0.01651 | 0/10 |
| page images only, cheap model | 10/10 | 100% | $0.00181 | $0.01805 | 0/10 |
| text + images, cheap model | 10/10 | 100% | $0.00192 | $0.01916 | 0/10 |
| text + images, strong model only | 10/10 | 100% | $0.01310 | $0.131 | 0/10 |
