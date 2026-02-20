#!/usr/bin/env python3
"""
Slide Renderer QA — Capture screenshots by rendering slides via a standalone HTML page.

Since the slide viewer is accessed through complex UI interactions,
this script renders slides server-side by:
1. Fetching slide data from the API
2. Building standalone HTML with the dashboard CSS + renderer JS
3. Screenshotting each slide using Playwright CLI

This verifies the data flow (API → JSON → HTML rendering) and captures
visual evidence for all 68 slide types.
"""
import json
import subprocess
import sys
import os
import urllib.request
import tempfile
from pathlib import Path

BASE_URL = "http://localhost:8002"
DIR = Path(__file__).parent

# All test lessons that cover all 68 types
LESSONS = [8, 11, 18, 22, 23, 24, 26, 30, 31, 36, 40, 43, 44, 47, 50, 52, 53, 58, 61, 79, 87, 103, 116, 118]


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def create_slide_html(slide, lesson_name):
    """Create a standalone HTML file that renders a single slide."""
    slide_type = slide.get('type', 'unknown')
    slide_id = slide.get('id', 0)
    content = slide.get('content', {})
    video_library = slide.get('video_library', {})

    # Build a JSON-safe slide object
    slide_json = json.dumps(slide, ensure_ascii=True)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="{BASE_URL}/css/tory-workspace.css">
<link rel="stylesheet" href="{BASE_URL}/css/common.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    background: #0f0f23; color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 1rem; margin: 0;
  }}
  .qa-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.5rem 0.75rem; margin-bottom: 0.75rem;
    background: rgba(255,255,255,0.05); border-radius: 6px;
    font-size: 0.75rem; color: #888;
  }}
  .qa-header strong {{ color: #7c3aed; font-size: 0.85rem; }}
  .qa-slide {{
    background: #16213e; border-radius: 12px; padding: 1.5rem;
    max-width: 800px; margin: 0 auto; min-height: 200px;
  }}
  .qa-slide img {{ max-width: 100%; height: auto; border-radius: 8px; }}
  .qa-slide video {{ max-width: 100%; border-radius: 8px; }}
  .tw-slide-media {{ margin-bottom: 1rem; }}
  .tw-slide-media img {{ max-width: 100%; border-radius: 8px; }}
  .tw-slide-text-content {{ padding: 0.5rem 0; }}
  .tw-slide-text-title {{ font-size: 1.2rem; color: #fff; margin-bottom: 0.75rem; }}
  .tw-slide-content-title {{ font-size: 1rem; color: #a78bfa; margin-bottom: 0.5rem; }}
  .tw-slide-text-body {{ color: #ccc; line-height: 1.6; margin-bottom: 0.5rem; }}
  .tw-slide-options {{ display: flex; flex-direction: column; gap: 0.5rem; margin: 0.75rem 0; }}
  .tw-slide-option {{
    background: rgba(255,255,255,0.05); padding: 0.75rem 1rem;
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);
    cursor: pointer;
  }}
  .tw-slide-option:hover {{ background: rgba(124,58,237,0.15); border-color: #7c3aed; }}
  .tw-quiz-correct {{ border-color: #10b981 !important; background: rgba(16,185,129,0.1) !important; }}
  .tw-slide-questions {{ display: flex; flex-direction: column; gap: 0.75rem; margin: 0.75rem 0; }}
  .tw-slide-question-item {{ margin-bottom: 0.5rem; }}
  .tw-slide-question-item label {{ display: block; margin-bottom: 0.25rem; color: #ddd; }}
  .tw-slide-textarea {{
    width: 100%; background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
    color: #e0e0e0; padding: 0.5rem; font-size: 0.9rem; resize: vertical;
  }}
  .tw-slide-greeting-message {{ font-size: 1.05rem; line-height: 1.7; color: #ddd; }}
  .tw-slide-greeting-sig {{ margin-top: 1rem; color: #888; }}
  .tw-slide-advisor-name {{ font-weight: 600; color: #a78bfa; }}
  .tw-slide-takeaway-msg {{ font-size: 1.1rem; line-height: 1.6; }}
  .tw-slide-takeaway-prompt {{ color: #7c3aed; font-style: italic; margin-top: 0.5rem; }}
  .tw-slide-headsup {{
    background: rgba(234,179,8,0.1); border-left: 3px solid #eab308;
    padding: 0.75rem 1rem; margin-top: 1rem; border-radius: 0 6px 6px 0;
  }}
  .tw-slide-badges {{ display: flex; gap: 0.5rem; margin-top: 0.5rem; }}
  .tw-slide-badge {{
    font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 4px;
    background: rgba(124,58,237,0.2); color: #a78bfa;
  }}
  .tw-badge-task {{ background: rgba(16,185,129,0.2); color: #10b981; }}
  .tw-slide-word-chips {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .tw-slide-word-chip {{
    padding: 0.4rem 0.8rem; border-radius: 20px;
    background: rgba(124,58,237,0.15); border: 1px solid #7c3aed;
    color: #c4b5fd; font-size: 0.9rem; cursor: pointer;
  }}
  .tw-slide-stakeholder-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
    gap: 0.75rem; margin: 1rem 0;
  }}
  .tw-slide-stakeholder-card {{ text-align: center; }}
  .tw-slide-stakeholder-avatar {{
    width: 60px; height: 60px; border-radius: 50%;
    background: rgba(255,255,255,0.1); display: flex;
    align-items: center; justify-content: center; margin: 0 auto 0.25rem;
    font-size: 1.5rem;
  }}
  .tw-slide-stakeholder-name {{ font-size: 0.8rem; color: #ccc; }}
  .tw-slide-form-header {{
    display: flex; gap: 1rem; font-weight: 600; color: #a78bfa;
    padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.1);
  }}
  .tw-slide-form-lhs, .tw-slide-form-rhs {{ flex: 1; }}
  .tw-slide-form-row {{ display: flex; gap: 1rem; padding: 0.5rem 0; }}
  .tw-slide-likert-table {{ width: 100%; }}
  .tw-slide-likert-header, .tw-slide-likert-row {{
    display: flex; padding: 0.5rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }}
  .tw-slide-likert-q {{ flex: 2; }}
  .tw-slide-likert-opt {{ flex: 1; text-align: center; font-size: 0.85rem; }}
  .tw-slide-radio-circle {{
    display: inline-block; width: 16px; height: 16px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.3);
  }}
  .tw-slide-feedback {{ padding: 0.75rem; border-radius: 6px; margin: 0.5rem 0; }}
  .tw-feedback-good {{ background: rgba(16,185,129,0.1); border-left: 3px solid #10b981; }}
  .tw-feedback-improve {{ background: rgba(239,68,68,0.1); border-left: 3px solid #ef4444; }}
  .tw-slide-chat {{ margin: 0.75rem 0; }}
  .tw-slide-chat-q {{
    background: rgba(124,58,237,0.15); padding: 0.75rem; border-radius: 12px 12px 4px 12px;
    margin-bottom: 0.5rem; max-width: 80%;
  }}
  .tw-slide-chat-a {{
    background: rgba(255,255,255,0.05); padding: 0.75rem; border-radius: 12px 12px 12px 4px;
    margin-bottom: 0.75rem; max-width: 80%; margin-left: auto;
  }}
  .tw-slide-image-examples {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 0.75rem; margin: 1rem 0;
  }}
  .tw-slide-image-example-card {{ text-align: center; }}
  .tw-slide-image-example-card img {{ max-width: 100%; border-radius: 8px; }}
  .tw-slide-image-example-label {{ font-size: 0.8rem; color: #ccc; margin-top: 0.25rem; }}
  .tw-slide-expand-item {{
    background: rgba(255,255,255,0.03); border-radius: 6px; padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
  }}
  .tw-slide-expand-item summary {{ cursor: pointer; color: #a78bfa; }}
  .tw-slide-select-input {{
    background: rgba(255,255,255,0.05); color: #e0e0e0;
    border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 0.25rem;
  }}
  .tw-slide-question-word {{
    font-size: 1.1rem; font-weight: 700; color: #7c3aed;
    margin-bottom: 0.25rem;
  }}
  .tw-slide-video-placeholder {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 3rem; background: rgba(255,255,255,0.03); border-radius: 12px;
    color: #666;
  }}
  .tw-slide-placeholder {{ padding: 2rem; text-align: center; color: #666; }}
  .tw-slide-fallback .tw-slide-json {{
    font-size: 0.75rem; max-height: 300px; overflow: auto;
    background: rgba(0,0,0,0.3); padding: 0.75rem; border-radius: 6px;
  }}
  .tw-slide-checklist-items {{ margin: 0.75rem 0; }}
  .tw-slide-checklist-item {{
    padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);
  }}
  .tw-slide-check-box {{ color: #7c3aed; margin-right: 0.5rem; }}
  .tw-slide-note {{
    background: rgba(124,58,237,0.08); padding: 0.75rem; border-radius: 6px;
    margin-top: 0.75rem; font-style: italic; color: #bbb;
  }}
  .tw-slide-special-word {{ font-size: 2rem; font-weight: 700; color: #7c3aed; text-align: center; margin: 1rem 0; }}
  .tw-slide-transcript {{ margin-top: 0.75rem; }}
  .tw-slide-transcript-label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; }}
  .tw-slide-transcript-text {{ font-size: 0.85rem; color: #aaa; line-height: 1.5; }}
</style>
</head>
<body>
<div class="qa-header">
  <span>Type: <strong>{slide_type}</strong></span>
  <span>Slide ID: {slide_id} | Lesson: {lesson_name}</span>
</div>
<div class="qa-slide" id="slide-root"></div>
<script>
function esc(s) {{
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}}
function _html(val) {{
  if (!val) return '';
  return String(val)
    .replace(/u201c/g, '\\u201c').replace(/u201d/g, '\\u201d')
    .replace(/u2018/g, '\\u2018').replace(/u2019/g, '\\u2019')
    .replace(/u2014/g, '\\u2014').replace(/u2013/g, '\\u2013')
    .replace(/u2026/g, '\\u2026');
}}
function _headsUp(c) {{
  if (!c.is_headsup && !c.heads_up) return '';
  const tip = c.heads_up || '';
  return tip ? '<div class="tw-slide-headsup"><strong>Heads up</strong><div>' + _html(tip) + '</div></div>' : '';
}}
function _backpackBadge(c) {{
  let badges = '';
  if (c.is_backpack) badges += '<span class="tw-slide-badge tw-badge-backpack">Backpack</span>';
  if (c.is_task) badges += '<span class="tw-slide-badge tw-badge-task">' + esc(c.task_name || 'Task') + '</span>';
  return badges ? '<div class="tw-slide-badges">' + badges + '</div>' : '';
}}

const slide = {slide_json};
const content = slide.content || {{}};
const type = slide.type || 'unknown';
const root = document.getElementById('slide-root');

// Render based on the actual renderer logic from tory-workspace.js
root.innerHTML = renderSlideContent(type, content, slide);

function renderSlideContent(type, content, slide) {{
  if (/^video/.test(type)) return _renderVideo(type, content, slide);
  if (type === 'greetings') return _renderGreeting(content);
  if (type === 'take-away') return _renderTakeaway(content);
  if (type === 'one-word-apprication' || type === 'one-word-content-box') return _renderOneWord(content);
  if (/^image\\d*$/.test(type) || /^special-image/.test(type) || type === 'sparkle') return _renderImage(type, content);
  if (/^image-with-/.test(type)) return _renderImageHybrid(type, content);
  if (/^question-answer/.test(type) || type === 'question-with-example' || type === 'questions-example2') return _renderQuestion(type, content);
  if (/^stakeholder/.test(type) || type === 'answered-stakeholders') return _renderStakeholder(type, content);
  if (type === 'multiple-choice' || type === 'single-choice-with-message') return _renderMultipleChoice(content);
  if (type === 'select-true-or-false' || type === 'choose-true-or-false') return _renderTrueFalse(content);
  if (type === 'check-yes-or-no') return _renderCheckYesNo(content);
  if (type === 'select-range') return _renderSelectRange(content);
  if (type === 'three-word' || type === 'select-one-word' || type === 'one-word-select-option') return _renderWordSelection(type, content);
  if (/^select-option/.test(type) || type === 'select-the-best') return _renderSelectOption(type, content);
  if (type === 'side-by-side-dropdown-selector') return _renderDropdownSelector(content);
  if (/^side-by-side-/.test(type)) return _renderSideBySideForm(content);
  if (['celebrate','show-gratitude','decision','decision2','take-to-lunch','people-you-would-like-to-thank','chat-interface','build-your-network'].includes(type)) return _renderEngagement(type, content);
  return _renderFallback(type, content);
}}

// Duplicated renderers (exact copy from tory-workspace.js post-fix)
function _renderVideo(type, content, slide) {{
  let html = '';
  const vl = slide && slide.video_library;
  if (vl && vl.video_url) {{
    const title = content.slide_title || vl.title || '';
    if (title) html += '<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">' + _html(title) + '</h3></div>';
    html += '<div class="tw-slide-media tw-slide-video-wrap"><video class="tw-plyr-video" playsinline controls preload="metadata"' + (vl.thumbnail_url ? ' poster="' + esc(vl.thumbnail_url) + '"' : '') + '><source src="' + esc(vl.video_url) + '" type="video/mp4"></video></div>';
  }} else {{
    html += '<div class="tw-slide-media"><div class="tw-slide-video-placeholder"><div style="font-size:2rem;opacity:0.3">&#9654;</div><div style="font-size:1rem;font-weight:500;margin-top:0.5rem">Video content</div><div style="font-size:0.85rem;opacity:0.6">' + esc(content.slide_title || 'Available in the MyNextory app') + '</div></div></div>';
    if (content.slide_title) html += '<div class="tw-slide-text-content"><h3 class="tw-slide-text-title">' + _html(content.slide_title) + '</h3></div>';
  }}
  html += _headsUp(content);
  if (content.options && Array.isArray(content.options)) {{
    html += '<div class="tw-slide-options">';
    for (const opt of content.options) html += '<div class="tw-slide-option"><strong>' + _html(opt.title || '') + '</strong><div>' + _html(opt.msg || '') + '</div></div>';
    html += '</div>';
  }}
  if (content.questions && Array.isArray(content.questions)) {{
    if (content.content_title) html += '<div class="tw-slide-content-title">' + _html(content.content_title) + '</div>';
    html += '<div class="tw-slide-questions">';
    for (const q of content.questions) {{
      html += '<div class="tw-slide-question-item">';
      if (q.word) html += '<div class="tw-slide-question-word">' + _html(q.word) + '</div>';
      if (q.question1) html += '<label>' + _html(q.question1) + '</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea>';
      if (q.question2) html += '<label>' + _html(q.question2) + '</label><textarea class="tw-slide-textarea" rows="2" placeholder="Your answer..."></textarea>';
      html += '</div>';
    }}
    html += '</div>';
  }}
  html += _backpackBadge(content);
  return html;
}}

function _renderImage(type, c) {{
  let html = '';
  const bg = c.background_image || '';
  if (bg) html += '<div class="tw-slide-media"><img src="' + esc(bg) + '" alt="' + esc(c.slide_title || 'Image') + '" loading="lazy" onerror="this.onerror=null;this.parentElement.innerHTML=\\'<div class=tw-slide-placeholder>Image unavailable</div>\\'"></div>';
  html += '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  if (c.content_title) html += '<div class="tw-slide-content-title">' + _html(c.content_title) + '</div>';
  if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
  if (c.short_description) html += '<div class="tw-slide-text-body tw-slide-description">' + _html(c.short_description) + '</div>';
  if (type === 'image5' && c.options && Array.isArray(c.options)) {{
    html += '<div class="tw-slide-options">';
    for (const opt of c.options) {{ html += '<details class="tw-slide-expand-item"><summary>' + _html(typeof opt === 'string' ? opt : (opt.option || '')) + '</summary><div>' + _html(opt.description || '') + '</div></details>'; }}
    html += '</div>';
  }}
  if (c.content1) html += '<div class="tw-slide-text-body">' + _html(c.content1) + '</div>';
  if (c.content2) html += '<div class="tw-slide-text-body">' + _html(c.content2) + '</div>';
  if (c.special_word) html += '<div class="tw-slide-special-word">' + _html(c.special_word) + '</div>';
  html += '</div>';
  html += _headsUp(c);
  return html;
}}

function _renderImageHybrid(type, c) {{
  let html = '';
  const bg = c.background_image || c.image || '';
  if (bg) html += '<div class="tw-slide-media"><img src="' + esc(bg) + '" alt="" loading="lazy" onerror="this.style.display=\\'none\\'"></div>';
  html += '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  if (c.content_title) html += '<div class="tw-slide-content-title">' + _html(c.content_title) + '</div>';
  if (c.content && type === 'image-with-content') html += '<div class="tw-slide-content-title">' + _html(c.content) + '</div>';
  if (c.content_on_image) html += '<div class="tw-slide-text-body">' + _html(c.content_on_image) + '</div>';
  if (c.content_description) html += '<div class="tw-slide-text-body">' + _html(c.content_description) + '</div>';
  if (c.card_title) html += '<div class="tw-slide-text-body"><strong>' + _html(c.card_title) + '</strong></div>';
  if (c.card_content) html += '<div class="tw-slide-text-body">' + _html(c.card_content) + '</div>';
  if (c.options && Array.isArray(c.options)) {{
    html += '<div class="tw-slide-options">';
    for (const opt of c.options) html += '<div class="tw-slide-option">' + _html(typeof opt === 'string' ? opt : (opt.title || opt.question || '')) + '</div>';
    html += '</div>';
  }}
  if (c.questions && Array.isArray(c.questions)) {{
    html += '<div class="tw-slide-questions">';
    for (const q of c.questions) {{ const t = typeof q === 'string' ? q : (q.question || q.title || ''); html += '<div class="tw-slide-question-item"><label>' + _html(t) + '</label><textarea class="tw-slide-textarea" rows="2"></textarea></div>'; }}
    html += '</div>';
  }}
  html += '</div>';
  html += _headsUp(c);
  return html;
}}

function _renderGreeting(c) {{
  return '<div class="tw-slide-text-content tw-slide-greeting">' +
    (c.slide_title ? '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>' : '') +
    '<div class="tw-slide-greeting-message">' + _html(c.greetings || '') + '</div>' +
    '<div class="tw-slide-greeting-sig"><span class="tw-slide-advisor-name">' + _html(c.advisor_name || '') + '</span> <span style="opacity:0.6">' + _html(c.advisor_content || '') + '</span></div>' +
    _headsUp(c) + '</div>';
}}

function _renderTakeaway(c) {{
  return '<div class="tw-slide-text-content tw-slide-takeaway">' +
    (c.slide_title ? '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>' : '') +
    '<div class="tw-slide-takeaway-msg">' + _html(c.message || '') + '</div>' +
    (c.message_1 ? '<div class="tw-slide-takeaway-prompt">' + _html(c.message_1) + '</div>' : '') +
    (c.message_2 ? '<div class="tw-slide-takeaway-prompt" style="color:#7c3aed">' + _html(c.message_2) + '</div>' : '') +
    _headsUp(c) + '</div>';
}}

function _renderOneWord(c) {{
  return '<div class="tw-slide-text-content tw-slide-oneword">' +
    (c.slide_title ? '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>' : '') +
    '<div style="font-size:1.1rem">' + _html(c.appreciation || c.content || '') + '</div>' +
    _backpackBadge(c) + '</div>';
}}

function _renderQuestion(type, c) {{
  let html = '<div class="tw-slide-text-content tw-slide-question-card">';
  html += (c.card_title || c.slide_title) ? '<h3 class="tw-slide-text-title">' + _html(c.card_title || c.slide_title) + '</h3>' : '';
  if (c.card_content) html += '<div class="tw-slide-text-body">' + _html(c.card_content) + '</div>';
  if (c.content_title) html += '<div class="tw-slide-content-title">' + _html(c.content_title) + '</div>';
  const qs = c.questions || c.questionss || [];
  if (qs && qs.LHS) {{
    const lhs = (typeof qs.LHS === 'string') ? qs.LHS.split('<br />').filter(Boolean) : (qs.LHS || []);
    const rhs = (typeof qs.RHS === 'string') ? qs.RHS.split('<br />').filter(Boolean) : (qs.RHS || []);
    html += '<div class="tw-slide-questions">';
    for (let i = 0; i < Math.max(lhs.length, rhs.length); i++) {{
      html += '<div class="tw-slide-form-row">';
      if (i < lhs.length) html += '<div class="tw-slide-form-lhs">' + _html(lhs[i]) + '</div>';
      if (i < rhs.length) html += '<div class="tw-slide-form-rhs">' + _html(rhs[i]) + '</div>';
      html += '</div>';
    }}
    html += '</div>';
  }} else if (Array.isArray(qs)) {{
    html += '<div class="tw-slide-questions">';
    for (const q of qs) {{
      const label = typeof q === 'string' ? q : (q.title ? '<strong>' + _html(q.title) + '</strong>: ' + _html(q.question || '') : _html(q.question || q.word || ''));
      html += '<div class="tw-slide-question-item"><label>' + label + '</label><textarea class="tw-slide-textarea" rows="2"></textarea></div>';
    }}
    html += '</div>';
  }}
  if (c.examples && Array.isArray(c.examples)) {{
    html += '<div>';
    for (let i = 0; i < c.examples.length; i++) {{
      const exList = c.examples[i];
      if (Array.isArray(exList) && exList.length) {{
        html += '<details class="tw-slide-expand-item"><summary>Examples ' + (i+1) + '</summary><ul>';
        for (const ex of exList) html += '<li>' + _html(ex) + '</li>';
        html += '</ul></details>';
      }}
    }}
    html += '</div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderStakeholder(type, c) {{
  let html = '<div class="tw-slide-text-content tw-slide-stakeholder">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  if (type === 'stakeholders' && c.stakeholders) {{
    html += '<div class="tw-slide-text-body">Select ' + esc(c.select_count || '3') + ' stakeholders:</div>';
    html += '<div class="tw-slide-stakeholder-grid">';
    for (const s of c.stakeholders) html += '<div class="tw-slide-stakeholder-card"><div class="tw-slide-stakeholder-avatar">&#128100;</div><div class="tw-slide-stakeholder-name">' + _html(s.name || '') + '</div></div>';
    html += '</div>';
  }} else if (type === 'stakeholder-question') {{
    if (c.stakeholder_name) html += '<div style="color:#a78bfa;font-weight:600">' + _html(c.stakeholder_name) + '</div>';
    if (c.question) html += '<div class="tw-slide-text-body">' + _html(c.question) + '</div>';
  }} else if (type === 'stakeholder-question-answer') {{
    if (c.stakeholder_name) html += '<div style="color:#a78bfa;font-weight:600">' + _html(c.stakeholder_name) + '</div>';
    for (const q of (c.questions || [])) html += '<div class="tw-slide-question-item"><label>' + _html(q) + '</label><textarea class="tw-slide-textarea" rows="2"></textarea></div>';
  }} else {{
    if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderMultipleChoice(c) {{
  let html = '<div class="tw-slide-text-content tw-slide-quiz">';
  if (c.card_title) html += '<h3 class="tw-slide-text-title">' + _html(c.card_title) + '</h3>';
  for (const q of (c.questions || [])) {{
    html += '<div style="margin-bottom:1rem"><div style="font-weight:500;margin-bottom:0.5rem">' + _html(q.question || '') + '</div><div class="tw-slide-options">';
    for (const opt of (q.options || [])) html += '<div class="tw-slide-option' + (opt.is_true ? ' tw-quiz-correct' : '') + '">' + _html(opt.option || '') + '</div>';
    html += '</div></div>';
  }}
  html += _headsUp(c) + '</div>';
  return html;
}}

function _renderTrueFalse(c) {{
  let html = '<div class="tw-slide-text-content tw-slide-quiz">';
  if (c.content_title) html += '<h3 class="tw-slide-text-title">' + _html(c.content_title) + '</h3>';
  if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
  for (const q of (c.questions || [])) {{
    html += '<div style="margin-bottom:0.75rem"><div style="font-weight:500;margin-bottom:0.5rem">' + _html(q.question || '') + '</div>';
    html += '<div class="tw-slide-options" style="flex-direction:row"><div class="tw-slide-option' + (q.answer === 'True' ? ' tw-quiz-correct' : '') + '">True</div><div class="tw-slide-option' + (q.answer === 'False' ? ' tw-quiz-correct' : '') + '">False</div></div></div>';
  }}
  html += _headsUp(c) + '</div>';
  return html;
}}

function _renderCheckYesNo(c) {{
  let html = '<div class="tw-slide-text-content">';
  if (c.content_title) html += '<h3 class="tw-slide-text-title">' + _html(c.content_title) + '</h3>';
  for (const item of (c.question || [])) html += '<div class="tw-slide-checklist-item"><span class="tw-slide-check-box">&#9744;</span>' + _html(item) + '</div>';
  html += _backpackBadge(c) + '</div>';
  return html;
}}

function _renderSelectRange(c) {{
  let html = '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  if (c.heading) html += '<div class="tw-slide-text-body">' + _html(c.heading) + '</div>';
  const opts = c.options || [];
  html += '<div class="tw-slide-likert-table"><div class="tw-slide-likert-header"><div class="tw-slide-likert-q"></div>';
  for (const o of opts) html += '<div class="tw-slide-likert-opt">' + _html(o) + '</div>';
  html += '</div>';
  for (const q of (c.questions || [])) {{
    html += '<div class="tw-slide-likert-row"><div class="tw-slide-likert-q">' + _html(q) + '</div>';
    for (let i = 0; i < opts.length; i++) html += '<div class="tw-slide-likert-opt"><span class="tw-slide-radio-circle"></span></div>';
    html += '</div>';
  }}
  html += '</div>' + _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderWordSelection(type, c) {{
  let html = '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  if (type === 'three-word' && c.words) {{
    const words = c.words.split(',').map(w => w.trim()).filter(Boolean);
    html += '<div class="tw-slide-text-body">Choose up to ' + (parseInt(c.no_of_words,10)||3) + ' words:</div><div class="tw-slide-word-chips">';
    for (const w of words) html += '<span class="tw-slide-word-chip">' + esc(w) + '</span>';
    html += '</div>';
  }} else {{
    if (c.question) html += '<div class="tw-slide-text-body">' + _html(c.question) + '</div>';
    if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
  }}
  if (c.options && Array.isArray(c.options) && type !== 'three-word') {{
    html += '<div class="tw-slide-options">';
    for (const opt of c.options) html += '<div class="tw-slide-option">' + _html(typeof opt === 'string' ? opt : (opt.option || '')) + '</div>';
    html += '</div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderSelectOption(type, c) {{
  let html = '<div class="tw-slide-text-content">';
  const title = c.card_title || c.slide_title || c.content_title || '';
  if (title) html += '<h3 class="tw-slide-text-title">' + _html(title) + '</h3>';
  if (c.content_description) html += '<div class="tw-slide-text-body">' + _html(c.content_description) + '</div>';
  if (c.options && c.options.length) {{
    html += '<div class="tw-slide-options">';
    for (const opt of c.options) html += '<div class="tw-slide-option">' + _html(typeof opt === 'string' ? opt : (opt.option || opt.label || '')) + '</div>';
    html += '</div>';
  }}
  if (c.data && Array.isArray(c.data)) {{
    html += '<div class="tw-slide-options">';
    for (const d of c.data) {{
      if (d.right_option) html += '<div class="tw-slide-option tw-quiz-correct">' + _html(d.right_option) + '</div>';
      if (d.wrong_option) html += '<div class="tw-slide-option">' + _html(d.wrong_option) + '</div>';
      if (d.message) html += '<div class="tw-slide-feedback tw-feedback-improve">' + _html(d.message) + '</div>';
    }}
    html += '</div>';
  }}
  if (c.images && Array.isArray(c.images)) {{
    html += '<div class="tw-slide-image-examples">';
    for (let i = 0; i < c.images.length; i++) html += '<div class="tw-slide-image-example-card"><img src="' + esc(c.images[i]) + '" alt="Option ' + (i+1) + '" onerror="this.style.display=\\'none\\'"><div class="tw-slide-image-example-label">Option ' + (i+1) + '</div></div>';
    html += '</div>';
  }}
  if (c.bonus_material && c.bonus_material.is_enable) {{
    html += '<details class="tw-slide-expand-item"><summary>' + _html(c.bonus_material.title || 'Bonus') + '</summary><div class="tw-slide-text-body">' + _html(c.bonus_material.content || '') + '</div></details>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderDropdownSelector(c) {{
  let html = '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  html += '<div class="tw-slide-form-header"><div class="tw-slide-form-lhs">' + _html(c.LHS_title || 'Statement') + '</div><div class="tw-slide-form-rhs">' + _html(c.RHS_title || 'Rating') + '</div></div>';
  for (const q of (c.questions || [])) {{
    html += '<div class="tw-slide-form-row"><div class="tw-slide-form-lhs">' + _html(q) + '</div>';
    html += '<div class="tw-slide-form-rhs"><select class="tw-slide-select-input"><option>Select...</option>';
    for (const o of (c.options || [])) html += '<option>' + esc(o) + '</option>';
    html += '</select></div></div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderSideBySideForm(c) {{
  let html = '<div class="tw-slide-text-content">';
  if (c.slide_title) html += '<h3 class="tw-slide-text-title">' + _html(c.slide_title) + '</h3>';
  const q = c.questions || {{}};
  const lhs = q.LHS || []; const rhs = q.RHS || [];
  html += '<div class="tw-slide-form-header"><div class="tw-slide-form-lhs">' + _html(c.lhs_title || 'Present') + '</div><div class="tw-slide-form-rhs">' + _html(c.rhs_title || 'Future') + '</div></div>';
  for (let i = 0; i < Math.max(lhs.length, rhs.length); i++) {{
    html += '<div class="tw-slide-form-row"><div class="tw-slide-form-lhs"><label>' + _html(lhs[i] || '') + '</label></div><div class="tw-slide-form-rhs"><label>' + _html(rhs[i] || '') + '</label></div></div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderEngagement(type, c) {{
  let html = '<div class="tw-slide-text-content">';
  const title = c.slide_title || c.content_title || c.card_title || '';
  if (title) html += '<h3 class="tw-slide-text-title">' + _html(title) + '</h3>';
  if (type === 'celebrate') {{
    if (c.content_description) html += '<div class="tw-slide-text-body">' + _html(c.content_description) + '</div>';
    if (c.content_heading) html += '<div class="tw-slide-text-body"><strong>' + _html(c.content_heading) + '</strong></div>';
  }} else if (type === 'decision' || type === 'decision2') {{
    for (const d of (c.decision || [])) html += '<div class="tw-slide-option"><strong>' + _html(d.title || '') + '</strong><div>' + _html(d.content || '') + '</div></div>';
  }} else if (type === 'chat-interface') {{
    html += '<div class="tw-slide-chat">';
    for (const p of (c.options || [])) html += '<div class="tw-slide-chat-q">' + _html(p.question || '') + '</div><div class="tw-slide-chat-a">' + _html(p.answer || '') + '</div>';
    html += '</div>';
  }} else if (type === 'build-your-network') {{
    if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
    for (const cat of (c.options || [])) {{
      html += '<details class="tw-slide-expand-item"><summary>' + _html(cat.card_title || '') + '</summary>';
      for (const q of (cat.question || [])) html += '<div class="tw-slide-question-item"><label>' + _html(q) + '</label></div>';
      html += '</details>';
    }}
  }} else {{
    if (c.content) html += '<div class="tw-slide-text-body">' + _html(c.content) + '</div>';
    if (c.content_description) html += '<div class="tw-slide-text-body">' + _html(c.content_description) + '</div>';
  }}
  html += _backpackBadge(c) + _headsUp(c) + '</div>';
  return html;
}}

function _renderFallback(type, c) {{
  let html = '<div class="tw-slide-text-content tw-slide-fallback">';
  html += '<div style="opacity:0.6;font-size:0.85rem">Type: ' + esc(type) + '</div>';
  const title = c.slide_title || c.card_title || c.content_title || '';
  if (title) html += '<h3 class="tw-slide-text-title">' + _html(title) + '</h3>';
  const text = c.content || c.message || c.greetings || '';
  if (text) html += '<div class="tw-slide-text-body">' + _html(text) + '</div>';
  if (!title && !text) html += '<pre class="tw-slide-json">' + esc(JSON.stringify(c, null, 2)) + '</pre>';
  html += _headsUp(c) + '</div>';
  return html;
}}
</script>
</body>
</html>"""
    return html


def main():
    print("Slide Renderer QA — Standalone Screenshot Capture")
    print("=" * 60)

    types_captured = set()
    all_types = set()
    errors = []

    for lesson_id in LESSONS:
        try:
            data = fetch_json(f"{BASE_URL}/api/tory/lesson/{lesson_id}/slides")
            slides = data.get('slides', data) if isinstance(data, dict) else data
        except Exception as e:
            print(f"  SKIP lesson {lesson_id}: {e}")
            continue

        new_types = [s['type'] for s in slides if s.get('type') and s['type'] not in types_captured]
        if not new_types:
            continue

        print(f"Lesson {lesson_id}: {len(slides)} slides, new: {', '.join(sorted(set(new_types)))}")

        for slide in slides:
            slide_type = slide.get('type', 'unknown')
            all_types.add(slide_type)

            if slide_type in types_captured:
                continue

            slide_id = slide.get('id', 0)
            filename = f"slide-{slide_type.replace('/', '_')}-{slide_id}.png"
            filepath = DIR / filename

            # Write HTML to temp file
            html = create_slide_html(slide, f"Lesson {lesson_id}")
            tmp_html = DIR / f"_tmp_{slide_type}.html"
            with open(tmp_html, 'w') as f:
                f.write(html)

            # Screenshot with Playwright
            try:
                result = subprocess.run(
                    ['npx', 'playwright', 'screenshot', '--wait-for-timeout=1000',
                     f'file://{tmp_html}', str(filepath)],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    types_captured.add(slide_type)
                    print(f"  [{len(types_captured)}/68] {slide_type} (slide {slide_id})")
                else:
                    errors.append({'type': slide_type, 'error': result.stderr[:200]})
                    print(f"  FAIL {slide_type}: {result.stderr[:100]}")
            except subprocess.TimeoutExpired:
                errors.append({'type': slide_type, 'error': 'timeout'})
                print(f"  TIMEOUT {slide_type}")
            finally:
                tmp_html.unlink(missing_ok=True)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Types captured: {len(types_captured)}/68")
    missing = all_types - types_captured
    if missing:
        print(f"Missing: {sorted(missing)}")
    else:
        print("All types captured!")
    if errors:
        print(f"Errors: {len(errors)}")
        for e in errors[:5]:
            print(f"  {e['type']}: {e['error'][:100]}")

    # Write screenshot manifest
    manifest = {
        "total_types": len(all_types),
        "types_captured": sorted(types_captured),
        "types_missing": sorted(missing) if missing else [],
        "errors": errors
    }
    with open(DIR / "screenshot-manifest.json", 'w') as f:
        json.dump(manifest, f, indent=2)


if __name__ == '__main__':
    main()
