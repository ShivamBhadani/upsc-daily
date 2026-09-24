/* UPSC Daily — public site.
   Vanilla JS, no build step, no dependencies. Data comes from static JSON files
   written by the desktop app's publisher; a visitor's answers and accuracy stay
   in their own browser (localStorage), never leaving the device. */

(function () {
  'use strict';

  var DATA = 'data/';
  var LETTERS = ['a', 'b', 'c', 'd'];
  var STORE_KEY = 'upscdaily.v1';

  var SUBJECT_COLOR = {
    'Polity & Governance': '#5b9bd5',
    'Economy': '#46b07f',
    'Environment & Ecology': '#5fbf9b',
    'Science & Technology': '#a97fd6',
    'History, Art & Culture': '#d9a441',
    'Geography': '#d98b5b',
    'International Relations': '#d96a9b',
    'Social Issues & Schemes': '#7fb0d6',
    'Mixed': '#8f97a8'
  };

  var NAV = [
    { href: '#/', glyph: '◉', label: 'Today' },
    { href: '#/news', glyph: '▤', label: 'Current affairs' },
    { href: '#/paper', glyph: '☷', label: 'Prelims paper' },
    { href: '#/quiz', glyph: '⏱', label: 'Quiz mode' },
    { href: '#/mains', glyph: '✎', label: 'Mains' },
    { href: '#/archive', glyph: '▣', label: 'Archive' },
    { href: '#/style', glyph: '⚖', label: 'PYQ style model' },
    { href: '#/progress', glyph: '◴', label: 'My progress' },
    { href: '#/about', glyph: '☰', label: 'About' }
  ];

  var index = null;      // data/index.json
  var style = null;      // data/style.json
  var dayCache = {};     // date -> payload
  var quiz = null;       // live quiz state
  var filters = { subject: 'all', format: 'all', search: '' };

  /* ------------------------------------------------------------ helpers -- */

  function el(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function subjectColor(s) { return SUBJECT_COLOR[s] || 'var(--muted)'; }

  // Source URLs come from a model reading news pages, so only ordinary web links
  // are ever put in an href — a javascript: or data: URL would run on click.
  function safeUrl(u) {
    var s = String(u == null ? '' : u).trim();
    return /^https?:\/\//i.test(s) ? s : '';
  }

  function chip(text, color) {
    return '<span class="chip" style="color:' + esc(color) + '">' + esc(text) + '</span>';
  }

  function prettyDate(iso) {
    if (!iso) return '';
    var p = iso.split('-');
    var months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
      'August', 'September', 'October', 'November', 'December'];
    var m = months[parseInt(p[1], 10) - 1] || p[1];
    return parseInt(p[2], 10) + ' ' + m + ' ' + p[0];
  }

  function bar(label, done, total, color, caption) {
    var pct = total ? Math.round(done / total * 100) : 0;
    return '<div class="bar"><div class="bar-top"><b>' + esc(label) + '</b>' +
      '<span class="muted">' + esc(caption || (done + '/' + total + ' · ' + pct + '%')) + '</span></div>' +
      '<div class="track"><div class="fill" style="width:' + pct + '%;background:' +
      esc(color) + '"></div></div></div>';
  }

  function fetchJSON(path) {
    return fetch(path, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(path + ' → HTTP ' + r.status);
      return r.json();
    });
  }

  /* ------------------------------------------------------- local storage -- */

  function loadProgress() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      var p = raw ? JSON.parse(raw) : null;
      if (!p || typeof p !== 'object') p = {};
      if (!p.attempts) p.attempts = {};
      if (!p.quizzes) p.quizzes = {};
      return p;
    } catch (e) {
      return { attempts: {}, quizzes: {} };
    }
  }

  function saveProgress(p) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(p)); } catch (e) { /* private mode */ }
  }

  function recordAttempt(q, chosen) {
    var p = loadProgress();
    p.attempts[q.id] = {
      chosen: chosen,
      correct: chosen === q.answer,
      subject: q.subject,
      qtype: q.qtype,
      date: q.id.split('#')[0]
    };
    saveProgress(p);
  }

  function recordQuiz(date, result) {
    var p = loadProgress();
    if (!p.quizzes[date]) p.quizzes[date] = [];
    p.quizzes[date].push(result);
    saveProgress(p);
  }

  /* -------------------------------------------------------------- theme -- */

  function currentTheme() {
    try { return localStorage.getItem('upscdaily.theme') || 'auto'; } catch (e) { return 'auto'; }
  }

  function applyTheme(mode) {
    if (mode === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', mode);
    try { localStorage.setItem('upscdaily.theme', mode); } catch (e) { /* ignore */ }
    var btn = el('theme-btn');
    if (btn) btn.textContent = mode === 'light' ? '☀' : (mode === 'dark' ? '☾' : '◐');
  }

  function cycleTheme() {
    var order = ['auto', 'dark', 'light'];
    var next = order[(order.indexOf(currentTheme()) + 1) % order.length];
    applyTheme(next);
  }

  /* ------------------------------------------------------------- routing -- */

  function parseHash() {
    var h = (location.hash || '#/').replace(/^#\/?/, '');
    var parts = h.split('/').filter(Boolean);
    var view = parts[0] || 'today';
    var date = null;
    // #/paper/2026-09-24  and  #/2026-09-24 both work
    if (/^\d{4}-\d{2}-\d{2}$/.test(view)) { date = view; view = 'paper'; }
    else if (parts[1] && /^\d{4}-\d{2}-\d{2}$/.test(parts[1])) date = parts[1];
    return { view: view, date: date };
  }

  function go(view, date) {
    location.hash = '#/' + view + (date ? '/' + date : '');
  }

  /* --------------------------------------------------------------- views -- */

  function renderNav(view, date) {
    var suffix = date ? '/' + date : '';
    return NAV.map(function (n) {
      var key = n.href.replace('#/', '') || 'today';
      var href = n.href === '#/' ? '#/' :
        (['news', 'paper', 'quiz', 'mains'].indexOf(key) >= 0 ? n.href + suffix : n.href);
      var on = (key === view || (key === 'today' && view === 'today')) ? ' class="on"' : '';
      return '<a href="' + href + '"' + on + '><span class="glyph">' + n.glyph +
        '</span>' + esc(n.label) + '</a>';
    }).join('');
  }

  function setChrome(view, date, title, sub) {
    el('nav').innerHTML = renderNav(view, date);
    el('page-title').textContent = title;
    el('page-sub').textContent = sub || '';
    document.title = title + ' · UPSC Daily';
    var picker = el('date-picker');
    if (!index || !index.days.length) { picker.innerHTML = ''; return; }
    var needsDate = ['news', 'paper', 'quiz', 'mains'].indexOf(view) >= 0;
    if (!needsDate) { picker.innerHTML = ''; return; }
    picker.innerHTML = '<select id="day-select" aria-label="Choose a day">' +
      index.days.map(function (d) {
        return '<option value="' + d.date + '"' + (d.date === date ? ' selected' : '') + '>' +
          prettyDate(d.date) + '</option>';
      }).join('') + '</select>';
    el('day-select').addEventListener('change', function () { go(view, this.value); });
  }

  function questionCard(q, state) {
    var p = loadProgress();
    var prev = p.attempts[q.id];
    var answered = state === 'reveal' || !!prev;
    var chosen = prev ? prev.chosen : null;

    var head = '<div class="q-head"><span class="q-num">Q' + q.n + '</span>' +
      chip(q.subject, subjectColor(q.subject)) +
      chip(q.difficulty, 'var(--muted)') +
      chip(q.qtypeName, 'var(--accent-dim)') +
      (q.origin === 'offline' ? chip('offline draft', 'var(--red)') : '') +
      '</div>';

    var body = '<p class="stem">' + esc(q.stem) + '</p>';
    if (q.statements && q.statements.length) {
      body += '<ul class="stmts">' + q.statements.map(function (s, i) {
        return '<li><span class="n">' + (i + 1) + '.</span> ' + esc(s) + '</li>';
      }).join('') + '</ul>';
    }
    if (q.pairs && q.pairs.length) {
      body += '<table class="pairs">' + q.pairs.map(function (pr) {
        return '<tr><td>' + esc(pr[0]) + '</td><td>' + esc(pr[1]) + '</td></tr>';
      }).join('') + '</table>';
    }
    if (q.closing) body += '<p class="closing">' + esc(q.closing) + '</p>';

    var opts = '<div class="opts">' + q.options.map(function (o, i) {
      var cls = 'opt';
      if (answered && i === q.answer) cls += ' right';
      else if (answered && chosen === i) cls += ' wrong';
      return '<button class="' + cls + '" type="button" data-q="' + esc(q.id) + '" data-i="' + i + '"' +
        (answered ? ' disabled' : '') + '><span class="key">' + LETTERS[i].toUpperCase() +
        '</span><span>' + esc(o) + '</span></button>';
    }).join('') + '</div>';

    var explain = '';
    if (answered) {
      var verdict = '';
      if (chosen !== null && chosen !== undefined) {
        verdict = chosen === q.answer
          ? '<span class="verdict ok">Correct.</span> '
          : '<span class="verdict no">Incorrect.</span> ';
      }
      explain = '<div class="explain">' + verdict + '<b>Answer: (' + LETTERS[q.answer] + ')</b><br>' +
        esc(q.explanation) +
        (q.pyqLink ? '<span class="link">' + esc(q.pyqLink) + '</span>' : '') + '</div>';
    }

    var hideSource = state === 'quiz' && !answered;   // the headline is a hint
    var qUrl = safeUrl(q.sourceUrl);
    var src = (qUrl && !hideSource)
      ? '<a class="src" href="' + esc(qUrl) + '" target="_blank" rel="noopener noreferrer">Source: ' +
        esc(q.sourceTitle || q.sourceUrl) + ' ↗</a>'
      : '';

    return '<article class="card q" data-qid="' + esc(q.id) + '">' + head + body + opts + explain + src + '</article>';
  }

  function viewToday(day) {
    var d = day;
    var html = '<div class="tiles">' +
      tile(d.counts.prelims, 'Prelims MCQs today', 'var(--accent)') +
      tile(d.counts.mains, 'Mains questions', 'var(--green)') +
      tile(d.counts.articles, 'news items behind them', 'var(--blue)') +
      tile(index.totals.days, 'papers in the archive', 'var(--muted)') +
      '</div>';

    html += '<div class="card"><h2>Paper for ' + esc(prettyDate(d.date)) + '</h2>' +
      '<div class="row no-print">' +
      '<a class="btn primary" href="#/paper/' + d.date + '">Read the paper</a>' +
      '<a class="btn" href="#/quiz/' + d.date + '">Take it as a timed test</a>' +
      '<a class="btn ghost" href="#/news/' + d.date + '">See the news behind it</a>' +
      '<a class="btn ghost" href="papers/' + d.date + '.html" target="_blank" rel="noopener">Printable version ↗</a>' +
      '</div></div>';

    var subjects = Object.keys(d.subjectCounts).sort(function (a, b) {
      return d.subjectCounts[b] - d.subjectCounts[a];
    });
    if (subjects.length) {
      html += '<div class="card"><h2>Subject spread</h2>' + subjects.map(function (s) {
        return bar(s, d.subjectCounts[s], d.counts.prelims, subjectColor(s));
      }).join('') + '</div>';
    }

    var formats = Object.keys(d.formatCounts).sort(function (a, b) {
      return d.formatCounts[b] - d.formatCounts[a];
    });
    if (formats.length) {
      html += '<div class="card"><h2>Question formats used</h2><div class="row tight">' +
        formats.map(function (f) {
          return chip(f + ' × ' + d.formatCounts[f], 'var(--accent-dim)');
        }).join('') + '</div></div>';
    }

    html += '<div class="card"><h2>How the questions are set</h2>' +
      '<p class="muted">Each day\'s news is read as a trigger, not as the answer. The paper is ' +
      'set against a model of previous year Prelims papers — the format mix, the subject ' +
      'weightage and the framing rules — so it reads like a UPSC paper rather than a news quiz. ' +
      '<a href="#/style">See the full model</a>.</p></div>';

    return html;
  }

  function tile(value, label, color) {
    return '<div class="card tile"><div class="val" style="color:' + color + '">' +
      esc(value) + '</div><div class="lbl">' + esc(label) + '</div></div>';
  }

  function viewPaper(day) {
    var qs = day.questions.filter(function (q) {
      if (filters.subject !== 'all' && q.subject !== filters.subject) return false;
      if (filters.format !== 'all' && q.qtype !== filters.format) return false;
      return true;
    });

    var subjects = Object.keys(day.subjectCounts).sort();
    var formats = [];
    var seen = {};
    day.questions.forEach(function (q) {
      if (!seen[q.qtype]) { seen[q.qtype] = 1; formats.push({ k: q.qtype, n: q.qtypeName }); }
    });

    var tools = '<div class="card no-print"><div class="row">' +
      '<select id="f-subject"><option value="all">All subjects</option>' +
      subjects.map(function (s) {
        return '<option value="' + esc(s) + '"' + (filters.subject === s ? ' selected' : '') + '>' +
          esc(s) + '</option>';
      }).join('') + '</select>' +
      '<select id="f-format"><option value="all">All formats</option>' +
      formats.map(function (f) {
        return '<option value="' + esc(f.k) + '"' + (filters.format === f.k ? ' selected' : '') + '>' +
          esc(f.n) + '</option>';
      }).join('') + '</select>' +
      '<span class="grow"></span>' +
      '<button class="btn" id="reveal-all" type="button">Reveal all answers</button>' +
      '<button class="btn ghost" id="reset-day" type="button">Clear my answers</button>' +
      '<button class="btn ghost" id="print-paper" type="button">Print / save PDF</button>' +
      '<button class="btn ghost" id="dl-md" type="button">Download Markdown</button>' +
      '</div></div>';

    if (!qs.length) return tools + '<p class="empty">No question matches these filters.</p>';
    return tools + qs.map(function (q) { return questionCard(q, 'practice'); }).join('');
  }

  function viewNews(day) {
    var needle = filters.search.toLowerCase();
    var arts = day.articles.filter(function (a) {
      if (!needle) return true;
      return (a.title + ' ' + a.summary).toLowerCase().indexOf(needle) >= 0;
    });
    var tools = '<div class="card no-print"><div class="row">' +
      '<input type="search" id="f-search" class="grow" placeholder="Search today\'s headlines…" value="' +
      esc(filters.search) + '"></div></div>';
    if (!arts.length) return tools + '<p class="empty">Nothing matches that search.</p>';
    return tools + arts.map(function (a) {
      return '<article class="card"><div class="row tight">' +
        chip(a.subject, subjectColor(a.subject)) +
        '<span class="grow"></span><span class="muted">' + esc(a.source) + '</span></div>' +
        '<div class="news-title">' + esc(a.title) + '</div>' +
        (a.summary ? '<p class="muted">' + esc(a.summary) + '</p>' : '') +
        '<div class="row"><span class="muted">' + esc(a.published || '') + '</span>' +
        '<span class="grow"></span>' +
        (safeUrl(a.url)
          ? '<a href="' + esc(safeUrl(a.url)) + '" target="_blank" rel="noopener noreferrer">Open article ↗</a>'
          : '') + '</div></article>';
    }).join('');
  }

  function viewMains(day) {
    if (!day.mains.length) return '<p class="empty">No Mains questions for this day.</p>';
    return day.mains.map(function (m) {
      return '<article class="card"><div class="q-head"><span class="q-num">' + m.n + '</span>' +
        chip(m.gsPaper, 'var(--blue)') + chip(m.marks + ' marks', 'var(--muted)') +
        chip(m.directive, 'var(--accent-dim)') + '</div>' +
        '<p class="stem">' + esc(m.question) + '</p>' +
        (m.hints.length ? '<p class="muted">Cover these dimensions:</p><ul class="stmts">' +
          m.hints.map(function (h) { return '<li><span class="n">•</span> ' + esc(h) + '</li>'; }).join('') +
          '</ul>' : '') +
        (safeUrl(m.sourceUrl) ? '<a class="src" href="' + esc(safeUrl(m.sourceUrl)) +
          '" target="_blank" rel="noopener noreferrer">Source: ' + esc(m.sourceTitle) + ' ↗</a>' : '') +
        '</article>';
    }).join('');
  }

  /* ---------------------------------------------------------------- quiz -- */

  function viewQuiz(day) {
    if (!day.questions.length) return '<p class="empty">No paper for this day.</p>';

    if (!quiz || quiz.date !== day.date) {
      return '<div class="card"><h2>Timed test — ' + esc(prettyDate(day.date)) + '</h2>' +
        '<p class="muted">' + day.questions.length + ' questions, UPSC marking: +2 for a correct ' +
        'answer, −0.66 for a wrong one, nothing for a skip. The clock starts when you do. ' +
        'Keys A–D or 1–4 mark an option; Enter moves on.</p>' +
        '<div class="row"><button class="btn primary" id="quiz-start" type="button">Start test</button>' +
        '<a class="btn ghost" href="#/paper/' + day.date + '">Read it untimed instead</a></div></div>';
    }

    if (quiz.done) {
      var total = day.questions.length;
      var attempted = quiz.right + quiz.wrong;
      var marks = quiz.right * 2 - quiz.wrong * (2 / 3);
      var acc = attempted ? Math.round(quiz.right / attempted * 100) : 0;
      var html = '<div class="card"><h2>Result</h2>' +
        '<div class="result-score">' + marks.toFixed(2) + ' / ' + (total * 2) + '</div>' +
        '<p class="muted">' + attempted + ' attempted of ' + total + ' · ' + quiz.right +
        ' correct · ' + quiz.wrong + ' incorrect · ' + clockText(quiz.elapsed) + ' taken</p>' +
        bar('Accuracy on attempted', quiz.right, Math.max(attempted, 1), 'var(--green)') +
        '<p class="muted">In the real paper the number that matters is accuracy on what you ' +
        'chose to attempt — ' + acc + '% here. Raise attempts only where the elimination is genuine.</p>' +
        '<div class="row"><button class="btn primary" id="quiz-again" type="button">Retake</button>' +
        '<a class="btn" href="#/paper/' + day.date + '">Review every question</a></div></div>';
      return html;
    }

    var q = day.questions[quiz.i];
    var pct = Math.round(quiz.i / day.questions.length * 100);
    var marksNow = quiz.right * 2 - quiz.wrong * (2 / 3);
    return '<div class="quiz-head"><span class="count">Question ' + (quiz.i + 1) + ' of ' +
      day.questions.length + '</span><span class="grow"></span>' +
      '<span class="score">' + quiz.right + ' right · ' + quiz.wrong + ' wrong · ' +
      marksNow.toFixed(2) + ' marks</span>' +
      '<span class="clock" id="clock">' + clockText(quiz.elapsed) + '</span></div>' +
      '<div class="bar"><div class="track"><div class="fill" style="width:' + pct +
      '%;background:var(--accent)"></div></div></div>' +
      questionCard(q, quiz.revealed ? 'reveal' : 'quiz') +
      '<div class="row no-print"><button class="btn ghost" id="quiz-skip" type="button">Skip</button>' +
      '<span class="grow"></span>' +
      '<button class="btn" id="quiz-next" type="button">' +
      (quiz.i + 1 >= day.questions.length ? 'Finish' : 'Next question') + '</button></div>';
  }

  function clockText(secs) {
    var m = Math.floor(secs / 60), s = secs % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function quizTick() {
    if (!quiz || quiz.done) return;
    quiz.elapsed += 1;
    var c = el('clock');
    if (c) c.textContent = clockText(quiz.elapsed);
  }

  function quizAdvance(day) {
    if (!quiz) return;
    if (quiz.i + 1 >= day.questions.length) {
      quiz.done = true;
      recordQuiz(day.date, {
        right: quiz.right, wrong: quiz.wrong,
        total: day.questions.length, seconds: quiz.elapsed
      });
    } else {
      quiz.i += 1;
      quiz.revealed = false;
    }
    render();
  }

  /* ------------------------------------------------------------ archive -- */

  function viewArchive() {
    if (!index.days.length) return '<p class="empty">No papers published yet.</p>';
    return '<div class="card"><h2>' + index.totals.days + ' papers · ' +
      index.totals.prelims + ' Prelims questions · ' + index.totals.mains +
      ' Mains questions</h2><p class="muted">Every day since this site started. Older papers ' +
      'stay exactly as they were set.</p></div>' +
      index.days.map(function (d) {
        var subs = Object.keys(d.subjects).sort(function (a, b) { return d.subjects[b] - d.subjects[a]; });
        return '<article class="card"><div class="archive-day">' +
          '<span class="date">' + esc(prettyDate(d.date)) + '</span>' +
          '<span class="muted">' + d.prelims + ' Prelims · ' + d.mains + ' Mains · ' +
          d.articles + ' news items</span><span class="grow"></span>' +
          '<a class="btn" href="#/paper/' + d.date + '">Paper</a>' +
          '<a class="btn ghost" href="#/quiz/' + d.date + '">Test</a></div>' +
          '<div class="row tight" style="margin-top:10px">' + subs.slice(0, 6).map(function (s) {
            return chip(s + ' ' + d.subjects[s], subjectColor(s));
          }).join('') + '</div></article>';
      }).join('');
  }

  /* -------------------------------------------------------------- style -- */

  function viewStyle() {
    if (!style) return '<p class="spinner">Loading…</p>';
    var html = '<div class="card"><h2>How this paper models UPSC style</h2>' +
      '<p>Every question is set against the pattern model below, distilled from previous year ' +
      'Prelims papers: the recurring question shapes and their share of a paper, the subject ' +
      'weightage, and the framing rules the Commission follows. The same model drives the ' +
      'prompt that sets the questions, so a day\'s paper looks like a UPSC paper rather than ' +
      'a news quiz.</p></div>';

    html += style.formats.map(function (f) {
      return '<article class="card"><div class="row tight"><h3 style="margin:0">' + esc(f.name) +
        '</h3>' + chip(f.share + '% of paper', 'var(--accent)') + '</div>' +
        '<p>' + esc(f.blueprint) + '</p>' +
        '<p class="muted"><i>' + esc(f.exemplar) + '</i></p>' +
        (f.options.length ? '<div class="row tight">' + f.options.map(function (o) {
          return chip(o, 'var(--muted)');
        }).join('') + '</div>' : '') + '</article>';
    }).join('');

    html += '<div class="card"><h2>Subject weightage targeted per paper</h2>' +
      Object.keys(style.subjectWeights).map(function (s) {
        var w = style.subjectWeights[s];
        return bar(s, w, 100, subjectColor(s), w + '% of the paper');
      }).join('') + '</div>';

    html += '<div class="card"><h2>Trends the setter follows</h2><ul class="stmts">' +
      style.trends.map(function (t, i) {
        return '<li><span class="n">' + (i + 1) + '.</span> ' + esc(t) + '</li>';
      }).join('') + '</ul></div>';

    html += '<div class="card"><h2>Mains</h2><p class="muted">Directive words: ' +
      esc(style.mainsDirectives.join(', ')) + '</p>' +
      Object.keys(style.mainsPapers).map(function (k) {
        return '<p><b>' + esc(k) + '</b> — ' + esc(style.mainsPapers[k]) + '</p>';
      }).join('') + '</div>';
    return html;
  }

  /* ----------------------------------------------------------- progress -- */

  function viewProgress() {
    var p = loadProgress();
    var ids = Object.keys(p.attempts);
    if (!ids.length) {
      return '<div class="card"><h2>Nothing tracked yet</h2><p class="muted">Answer a few ' +
        'questions — in the paper or in a timed test — and your subject-wise accuracy builds ' +
        'up here. It is stored in this browser only, never uploaded.</p>' +
        '<a class="btn primary" href="#/paper">Open today\'s paper</a></div>';
    }

    var bySubject = {}, byFormat = {}, days = {}, right = 0;
    ids.forEach(function (id) {
      var a = p.attempts[id];
      var s = a.subject || 'Mixed';
      if (!bySubject[s]) bySubject[s] = { n: 0, ok: 0 };
      bySubject[s].n += 1;
      if (a.correct) { bySubject[s].ok += 1; right += 1; }
      var f = a.qtype || 'other';
      if (!byFormat[f]) byFormat[f] = { n: 0, ok: 0 };
      byFormat[f].n += 1;
      if (a.correct) byFormat[f].ok += 1;
      days[a.date] = 1;
    });

    var marks = right * 2 - (ids.length - right) * (2 / 3);
    var html = '<div class="tiles">' +
      tile(ids.length, 'questions attempted', 'var(--accent)') +
      tile(Math.round(right / ids.length * 100) + '%', 'overall accuracy', 'var(--green)') +
      tile(Object.keys(days).length, 'days practised', 'var(--blue)') +
      tile(marks.toFixed(1), 'net marks, UPSC scoring', 'var(--muted)') +
      '</div>';

    html += '<div class="card"><h2>Accuracy by subject</h2>' +
      Object.keys(bySubject).sort(function (a, b) { return bySubject[b].n - bySubject[a].n; })
        .map(function (s) { return bar(s, bySubject[s].ok, bySubject[s].n, subjectColor(s)); })
        .join('') + '</div>';

    var names = {};
    if (style) style.formats.forEach(function (f) { names[f.key] = f.name; });
    html += '<div class="card"><h2>Accuracy by question format</h2>' +
      Object.keys(byFormat).sort(function (a, b) { return byFormat[b].n - byFormat[a].n; })
        .map(function (f) {
          return bar(names[f] || f, byFormat[f].ok, byFormat[f].n, 'var(--accent)');
        }).join('') + '</div>';

    var quizDates = Object.keys(p.quizzes).sort().reverse();
    if (quizDates.length) {
      html += '<div class="card"><h2>Timed tests</h2>' + quizDates.map(function (d) {
        return p.quizzes[d].map(function (r) {
          var m = r.right * 2 - r.wrong * (2 / 3);
          return '<p>' + esc(prettyDate(d)) + ' — <b>' + m.toFixed(2) + '/' + (r.total * 2) +
            '</b> <span class="muted">(' + r.right + ' right, ' + r.wrong + ' wrong, ' +
            clockText(r.seconds) + ')</span></p>';
        }).join('');
      }).join('') + '</div>';
    }

    html += '<div class="card no-print"><h2>This data lives in your browser</h2>' +
      '<p class="muted">Nothing here is uploaded. Clearing your browser data clears it.</p>' +
      '<div class="row"><button class="btn ghost" id="export-progress" type="button">Download my record</button>' +
      '<button class="btn ghost" id="wipe-progress" type="button">Erase everything</button></div></div>';
    return html;
  }

  /* -------------------------------------------------------------- about -- */

  function viewAbout() {
    return '<div class="card"><h2>What this is</h2>' +
      '<p>A daily UPSC practice paper built from the day\'s current affairs. News is collected ' +
      'from PIB, The Hindu, Indian Express, Down To Earth, Mint and the Economic Times, read ' +
      'in full, and then turned into at least 20 Prelims MCQs and a set of Mains questions in ' +
      'the formats UPSC actually uses.</p>' +
      '<p>The news is only the trigger. What each question tests is the static syllabus behind ' +
      'the headline — the institution, the law, the ecology, the economics, the geography. ' +
      '<a href="#/style">The full pattern model is published here</a>, so you can see exactly ' +
      'what the paper is aiming at.</p></div>' +
      '<div class="card"><h2>How to use it</h2>' +
      '<p><b>Read</b> the paper untimed, answering as you go — each question reveals its answer ' +
      'and reasoning as soon as you choose.<br>' +
      '<b>Test</b> yourself with the timed run: +2 for a correct answer, −0.66 for a wrong one, ' +
      'exactly like the real Prelims.<br>' +
      '<b>Track</b> where you are weak on the progress page.<br>' +
      '<b>Print</b> any day\'s paper for offline practice.</p></div>' +
      '<div class="card"><h2>Honesty about the questions</h2>' +
      '<p>Questions are set by a language model against the pattern model, from the article text, ' +
      'with a source link on every question. They are practice material, not an official paper. ' +
      'Check anything that surprises you against the source — a question badged ' +
      '<span class="chip" style="color:var(--red)">OFFLINE DRAFT</span> was built by the ' +
      'fallback template engine and deserves more scepticism than the rest.</p>' +
      '<p class="muted">Last built: ' + esc(index ? index.generatedAt : '—') + '</p></div>';
  }

  /* ------------------------------------------------------------- exports -- */

  function download(name, text, mime) {
    var blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function paperMarkdown(day) {
    var out = ['# UPSC Daily — ' + day.date, ''];
    day.questions.forEach(function (q) {
      out.push('**Q' + q.n + '. ' + q.stem + '**', '');
      (q.statements || []).forEach(function (s, i) { out.push((i + 1) + '. ' + s); });
      (q.pairs || []).forEach(function (p) { out.push('- ' + p[0] + ' — ' + p[1]); });
      if (q.closing) out.push('', '*' + q.closing + '*');
      out.push('');
      q.options.forEach(function (o, i) { out.push('(' + LETTERS[i] + ') ' + o); });
      out.push('');
    });
    out.push('## Answer key', '');
    day.questions.forEach(function (q) {
      out.push('**Q' + q.n + ': (' + LETTERS[q.answer] + ')** — ' + q.explanation);
      if (safeUrl(q.sourceUrl)) out.push('  Source: ' + q.sourceUrl);
      out.push('');
    });
    if (day.mains.length) {
      out.push('## Mains', '');
      day.mains.forEach(function (m) {
        out.push('**' + m.n + '. [' + m.gsPaper + ' · ' + m.marks + ' marks]** ' + m.question);
        m.hints.forEach(function (h) { out.push('   - ' + h); });
        out.push('');
      });
    }
    return out.join('\n');
  }

  /* --------------------------------------------------------------- shell -- */

  var TITLES = {
    today: 'Today', paper: 'Prelims paper', quiz: 'Quiz mode', mains: 'Mains',
    news: 'Current affairs', archive: 'Archive', style: 'PYQ style model',
    progress: 'My progress', about: 'About'
  };

  function render() {
    var route = parseHash();
    var view = TITLES[route.view] ? route.view : 'today';
    var date = route.date || (index ? index.latest : null);
    var body = el('view');

    if (view === 'style') {
      setChrome(view, null, TITLES[view], 'The pattern model every question is set against');
      body.innerHTML = viewStyle();
      return;
    }
    if (view === 'progress') {
      setChrome(view, null, TITLES[view], 'Kept in this browser, never uploaded');
      body.innerHTML = viewProgress();
      return;
    }
    if (view === 'archive') {
      setChrome(view, null, TITLES[view], 'Every paper published so far');
      body.innerHTML = viewArchive();
      return;
    }
    if (view === 'about') {
      setChrome(view, null, TITLES[view], 'What this is and how to use it');
      body.innerHTML = viewAbout();
      return;
    }

    if (!date) {
      setChrome(view, null, TITLES[view], '');
      body.innerHTML = '<p class="empty">No paper has been published yet.</p>';
      return;
    }

    loadDay(date).then(function (day) {
      var subs = {
        today: prettyDate(day.date) + ' · everything at a glance',
        paper: day.counts.prelims + ' questions in UPSC Prelims format · ' + prettyDate(day.date),
        quiz: 'UPSC marking: +2 correct, −0.66 wrong · ' + prettyDate(day.date),
        mains: day.counts.mains + ' answer-writing questions · ' + prettyDate(day.date),
        news: day.counts.articles + ' items collected on ' + prettyDate(day.date)
      };
      setChrome(view, date, TITLES[view], subs[view] || '');
      if (view === 'today') body.innerHTML = viewToday(day);
      else if (view === 'paper') body.innerHTML = viewPaper(day);
      else if (view === 'news') body.innerHTML = viewNews(day);
      else if (view === 'mains') body.innerHTML = viewMains(day);
      else if (view === 'quiz') body.innerHTML = viewQuiz(day);
      window.scrollTo(0, 0);
    }).catch(function (err) {
      setChrome(view, date, TITLES[view], '');
      body.innerHTML = '<div class="card"><h2>That paper could not be loaded</h2>' +
        '<p class="muted">' + esc(err.message) + '</p>' +
        '<a class="btn" href="#/archive">Back to the archive</a></div>';
    });
  }

  function loadDay(date) {
    if (dayCache[date]) return Promise.resolve(dayCache[date]);
    return fetchJSON(DATA + date + '.json').then(function (d) {
      dayCache[date] = d;
      return d;
    });
  }

  /* -------------------------------------------------------------- events -- */

  function onClick(ev) {
    var t = ev.target;

    var opt = t.closest ? t.closest('.opt') : null;
    if (opt && !opt.disabled) {
      var qid = opt.getAttribute('data-q');
      var chosen = parseInt(opt.getAttribute('data-i'), 10);
      var date = qid.split('#')[0];
      loadDay(date).then(function (day) {
        var q = day.questions.filter(function (x) { return x.id === qid; })[0];
        if (!q) return;
        recordAttempt(q, chosen);
        if (quiz && !quiz.done && quiz.date === date) {
          if (chosen === q.answer) quiz.right += 1; else quiz.wrong += 1;
          quiz.revealed = true;
          render();
          setTimeout(function () {
            if (quiz && !quiz.done) quizAdvance(day);
          }, 1500);
        } else {
          var card = document.querySelector('[data-qid="' + qid.replace(/"/g, '') + '"]');
          if (card) card.outerHTML = questionCard(q, 'practice');
        }
      });
      return;
    }

    if (t.id === 'theme-btn') { cycleTheme(); return; }
    if (t.id === 'burger') { document.body.classList.toggle('nav-open'); return; }
    if (t.id === 'scrim') { document.body.classList.remove('nav-open'); return; }

    if (t.id === 'reveal-all') {
      var route = parseHash();
      loadDay(route.date || index.latest).then(function (day) {
        var p = loadProgress();
        day.questions.forEach(function (q) {
          if (!p.attempts[q.id]) {
            p.attempts[q.id] = { chosen: null, correct: false, subject: q.subject,
              qtype: q.qtype, date: day.date, revealed: true };
          }
        });
        saveProgress(p);
        render();
      });
      return;
    }

    if (t.id === 'reset-day') {
      var r2 = parseHash();
      var d2 = r2.date || index.latest;
      var p2 = loadProgress();
      Object.keys(p2.attempts).forEach(function (id) {
        if (id.indexOf(d2 + '#') === 0) delete p2.attempts[id];
      });
      saveProgress(p2);
      render();
      return;
    }

    if (t.id === 'print-paper') { window.print(); return; }

    if (t.id === 'dl-md') {
      var r3 = parseHash();
      loadDay(r3.date || index.latest).then(function (day) {
        download('upsc-daily-' + day.date + '.md', paperMarkdown(day), 'text/markdown;charset=utf-8');
      });
      return;
    }

    if (t.id === 'quiz-start' || t.id === 'quiz-again') {
      var r4 = parseHash();
      var d4 = r4.date || index.latest;
      var p4 = loadProgress();
      Object.keys(p4.attempts).forEach(function (id) {
        if (id.indexOf(d4 + '#') === 0) delete p4.attempts[id];
      });
      saveProgress(p4);
      quiz = { date: d4, i: 0, right: 0, wrong: 0, elapsed: 0, done: false, revealed: false };
      render();
      return;
    }

    if (t.id === 'quiz-next' || t.id === 'quiz-skip') {
      var r5 = parseHash();
      loadDay(r5.date || index.latest).then(quizAdvance);
      return;
    }

    if (t.id === 'export-progress') {
      download('upsc-daily-progress.json', JSON.stringify(loadProgress(), null, 2), 'application/json');
      return;
    }

    if (t.id === 'wipe-progress') {
      if (window.confirm('Erase every answer and test result stored in this browser?')) {
        saveProgress({ attempts: {}, quizzes: {} });
        quiz = null;
        render();
      }
      return;
    }

    var link = t.closest ? t.closest('a[href^="#/"]') : null;
    if (link) document.body.classList.remove('nav-open');
  }

  function onKey(ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    var key = ev.key.toLowerCase();
    var i = 'abcd'.indexOf(key);
    if (i < 0 && '1234'.indexOf(key) >= 0) i = parseInt(key, 10) - 1;
    if (i >= 0) {
      var btns = document.querySelectorAll('.card.q .opt');
      if (btns.length === 4 && !btns[i].disabled) { btns[i].click(); ev.preventDefault(); }
      return;
    }
    if (key === 'enter' || key === 'n') {
      var next = el('quiz-next');
      if (next) { next.click(); ev.preventDefault(); }
    }
  }

  function onChange(ev) {
    if (ev.target.id === 'f-subject') { filters.subject = ev.target.value; render(); }
    if (ev.target.id === 'f-format') { filters.format = ev.target.value; render(); }
  }

  function onInput(ev) {
    if (ev.target.id === 'f-search') {
      filters.search = ev.target.value;
      var day = dayCache[parseHash().date || index.latest];
      if (day) {
        el('view').innerHTML = viewNews(day);
        var box = el('f-search');
        if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
      }
    }
  }

  /* ---------------------------------------------------------------- boot -- */

  function boot() {
    applyTheme(currentTheme());
    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    document.addEventListener('input', onInput);
    document.addEventListener('keydown', onKey);
    window.addEventListener('hashchange', function () {
      var r = parseHash();
      if (quiz && r.view !== 'quiz') quiz = null;
      render();
    });
    setInterval(quizTick, 1000);

    Promise.all([fetchJSON(DATA + 'index.json'), fetchJSON(DATA + 'style.json')])
      .then(function (res) {
        index = res[0];
        style = res[1];
        el('built').textContent = 'Built ' + index.generatedAt;
        render();
      })
      .catch(function (err) {
        el('view').innerHTML = '<div class="card"><h2>Could not load the site data</h2>' +
          '<p class="muted">' + esc(err.message) + '</p></div>';
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
