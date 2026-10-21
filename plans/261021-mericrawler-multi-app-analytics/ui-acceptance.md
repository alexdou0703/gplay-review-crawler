# Mericrawler UI acceptance checklist

- [x] Visible product name is Mericrawler in the page title, header, footer, CSS
      classes, and README.
- [x] Queue input accepts one app per line and shows independent job cards.
- [x] Job cards expose text status, progress, last event, cancel, retry, and error reason.
- [x] Selected package context remains visible while other jobs are queued or running.
- [x] Analysis labels language as a market proxy and groups long language tails into `Other`.
- [x] Queue panel uses native Streamlit fragments when available and a refresh fallback otherwise.
- [x] Manual narrow viewport/keyboard/reduced-motion pass completed in Chrome; focus outline and CSS media rule verified.
