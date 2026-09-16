/* Client-side finder for the public report template library.
   Matching mirrors web/report_templates.py search_entries(): drop stopwords,
   then require every remaining word to start a word in the card's search text.
   Nothing is sent to the server; the query only updates the page URL. */
(() => {
  const form = document.getElementById('library-finder');
  const input = document.getElementById('template-search');
  const status = document.getElementById('template-search-status');
  const empty = document.getElementById('library-empty');
  if (!form || !input || !status || !empty) return;

  const stopwords = new Set((form.dataset.stopwords || '').split(/\s+/).filter(Boolean));
  const filters = Array.from(form.querySelectorAll('.library-filter'));
  const groups = Array.from(document.querySelectorAll('.library-group'));
  const cards = Array.from(document.querySelectorAll('.template-card')).map((el) => ({
    el,
    group: el.dataset.group,
    words: (el.dataset.search || '').split(' '),
    title: el.querySelector('h3').textContent,
    href: el.getAttribute('href'),
  }));
  const total = cards.length;
  const emptyQuery = document.getElementById('library-empty-query');
  const emptyLede = document.getElementById('library-empty-lede');
  const closest = document.getElementById('library-closest');
  const reset = document.getElementById('library-empty-reset');
  let modality = 'all';

  const tokens = (query) => {
    const seen = [];
    query.toLowerCase().replace(/[^a-z0-9]+/g, ' ').split(' ').forEach((w) => {
      if (w && !stopwords.has(w) && !seen.includes(w)) seen.push(w);
    });
    return seen;
  };
  const hits = (words, toks) => toks.filter((t) => words.some((w) => w.startsWith(t))).length;

  const renderClosest = (toks) => {
    closest.textContent = '';
    const scored = cards
      .map((c) => ({ c, score: hits(c.words, toks) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 4);
    scored.forEach(({ c }) => {
      const a = document.createElement('a');
      a.href = c.href;
      a.textContent = c.title;
      closest.appendChild(a);
    });
    if (scored.length) {
      emptyLede.textContent = 'The closest templates share a modality or a body region with your search. Open one to reuse its section checklist.';
    } else {
      emptyLede.textContent = 'Try a study name, a body region or an abbreviation such as CTPA, DVT or MRCP.';
    }
  };

  const apply = () => {
    const query = input.value.trim();
    const toks = tokens(query);
    let shown = 0;
    cards.forEach((c) => {
      const ok = (modality === 'all' || c.group === modality) && hits(c.words, toks) === toks.length;
      c.el.hidden = !ok;
      if (ok) shown += 1;
    });
    groups.forEach((g) => {
      g.hidden = !g.querySelector('.template-card:not([hidden])');
    });
    const noMatch = shown === 0;
    empty.hidden = !noMatch;
    if (noMatch) {
      emptyQuery.textContent = query || 'this modality';
      renderClosest(toks);
    }
    const label = filters.find((f) => f.dataset.modality === modality);
    const scope = modality === 'all' ? '' : ` in ${label.textContent}`;
    if (!toks.length && modality === 'all') {
      status.textContent = `${total} templates across ${groups.length} modality groups.`;
    } else if (noMatch) {
      status.textContent = `No match${scope}. Closest templates are listed below.`;
    } else {
      status.textContent = `${shown} of ${total} templates${scope}${toks.length ? ` match “${query}”` : ''}.`;
    }
    const url = new URL(window.location.href);
    if (query) url.searchParams.set('q', query); else url.searchParams.delete('q');
    if (modality !== 'all') url.searchParams.set('modality', modality); else url.searchParams.delete('modality');
    window.history.replaceState(null, '', url.pathname + url.search + (query || modality !== 'all' ? '' : url.hash));
  };

  const setModality = (next) => {
    modality = next;
    filters.forEach((f) => {
      const active = f.dataset.modality === modality;
      f.classList.toggle('is-active', active);
      f.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    apply();
  };

  filters.forEach((f) => {
    f.setAttribute('role', 'button');
    f.addEventListener('click', (event) => {
      event.preventDefault();
      setModality(f.dataset.modality);
    });
  });
  input.addEventListener('input', apply);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    apply();
  });
  reset.addEventListener('click', (event) => {
    event.preventDefault();
    input.value = '';
    setModality('all');
    input.focus();
  });

  const params = new URLSearchParams(window.location.search);
  const initialModality = params.get('modality');
  if (initialModality && filters.some((f) => f.dataset.modality === initialModality)) {
    modality = initialModality;
  }
  setModality(modality);
})();
