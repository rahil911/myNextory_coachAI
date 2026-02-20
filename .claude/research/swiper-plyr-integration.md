# Swiper + Plyr Integration Recommendations
> Agent: ace2b01 (Context7 research) | Date: 2026-02-20

## 1. Swiper Configuration

```javascript
const lessonSwiper = new Swiper('.lesson-swiper', {
  direction: 'horizontal',
  autoHeight: true,
  spaceBetween: 0,
  slidesPerView: 1,
  navigation: {
    nextEl: '.swiper-button-next',
    prevEl: '.swiper-button-prev',
  },
  pagination: {
    el: '.swiper-pagination',
    type: 'fraction',
    formatFractionCurrent: (n) => String(n).padStart(2, '0'),
    formatFractionTotal: (n) => String(n).padStart(2, '0'),
  },
  keyboard: { enabled: true, onlyInViewport: true },
  a11y: {
    prevSlideMessage: 'Previous slide',
    nextSlideMessage: 'Next slide',
    containerRoleDescriptionMessage: 'lesson slides',
    itemRoleDescriptionMessage: 'slide',
  },
  lazyPreloadPrevNext: 1,
  focusableElements: 'input, select, option, textarea, button, video, audio, label, [role="radio"], [role="checkbox"]',
  observer: true,
  observeParents: true,
  observeSlideChildren: true,
  on: {
    init: onSwiperInit,
    slideChangeTransitionEnd: onSlideChanged,
    slideChangeTransitionStart: onSlideLeaving,
  },
});
```

### Why These Choices
- **autoHeight**: Slides vary dramatically (video 16:9 vs text 150px vs quiz 600px)
- **fraction pagination**: 2-29 slides per lesson makes dots unusable past ~10
- **lazyPreloadPrevNext: 1**: Preload adjacent but not all 29 slides
- **observer: true**: Interactive slides add/remove DOM dynamically
- **focusableElements expanded**: Include [role="radio"]/[role="checkbox"] for quiz slides

## 2. Slide Rendering Templates

### 2.1 Image + Audio Slide
```html
<div class="swiper-slide slide-type-image">
  <div class="slide-image-container">
    <img data-src="${blobUrl}/${slide.background_image}${sas}" loading="lazy"
         alt="${slide.slide_title || 'Lesson illustration'}"
         onerror="this.src='/assets/img/slide-fallback.svg';" />
  </div>
  <div class="slide-content-overlay">
    ${slide.slide_title ? `<h2>${slide.slide_title}</h2>` : ''}
    ${slide.content ? `<p>${slide.content}</p>` : ''}
  </div>
  ${slide.audio ? `<audio class="plyr-audio"><source src="${blobUrl}/${slide.audio}${sas}" type="audio/mp3"></audio>` : ''}
  ${slide.is_headsup ? `<details class="slide-headsup"><summary>Heads up</summary>${slide.heads_up}</details>` : ''}
</div>
```

### 2.2 Video Slide
- Load `video_library_id` → `video_libraries` → extract HLS URL from `url` JSON
- Poster from `thumbnail` field
- HLS source + MP4 fallback

### 2.3 Greeting/Text Slide
- `slide_title` + `greetings` (long message) + `advisor_name`/`advisor_content`

### 2.4 Take-Away Slide
- `message` (key takeaway, may contain DYNAMIC_WORD) + `message_1`/`message_2` (rating prompts)

### 2.5 Interactive Select Slide
- Options as selectable cards/chips
- Radio/checkbox per select type

### 2.6 Question/Open-Ended Slide
- Card with `card_title`/`card_content` + textarea per question
- Example toggle buttons

## 3. Plyr Integration Pattern

### Lazy Init Strategy
```javascript
const plyrInstances = new Map();

function initPlyrForSlide(slideIndex) {
  if (plyrInstances.has(slideIndex)) return;
  const slideEl = swiper.slides[slideIndex];
  // Init video or audio Plyr with appropriate controls
  // Store in map
}

function destroyPlyrForSlide(slideIndex) {
  const instance = plyrInstances.get(slideIndex);
  if (instance) { instance.player.destroy(); plyrInstances.delete(slideIndex); }
}
```

### Slide Change Hooks
- onSlideLeaving: pause ALL active media
- onSlideChanged: init active +/- 1, destroy > 2 away, recalc height

## 4. HLS Streaming with hls.js

```javascript
function initVideoWithHls(videoElement, hlsUrl, fallbackMp4Url) {
  if (Hls.isSupported()) {
    const hls = new Hls({ maxBufferLength: 30, startLevel: -1 });
    hls.loadSource(hlsUrl);
    hls.attachMedia(videoElement);
    hls.on(Hls.Events.ERROR, (e, data) => {
      if (data.fatal) { hls.destroy(); videoElement.src = fallbackMp4Url; }
    });
  } else if (videoElement.canPlayType('application/vnd.apple.mpegurl')) {
    videoElement.src = hlsUrl; // Safari native HLS
  } else {
    videoElement.src = fallbackMp4Url; // Direct MP4
  }
}
```

## 5. Image Error Handling
- Fallback SVG on 404
- Retry with fresh SAS token once
- CSS: `.image-failed` gets gradient background

## 6. Accessibility
- `role="region"` + `aria-roledescription="carousel"` on container
- `aria-label="Slide N of M: title"` on each slide
- Hidden slides: `aria-hidden="true"` + `tabindex="-1"` on focusables
- `aria-live="polite"` on pagination
- No focus trap — tab exits carousel naturally

## 7. Height Strategy
- `autoHeight: true` + CSS minimums per type
- `.swiper-wrapper { align-items: flex-start }` (not stretch)
- Video: `padding-top: 56.25%` (16:9 aspect)
- Image: `max-height: 60vh; object-fit: contain`
- Interactive: `min-height: 400px`
- Text: `min-height: 250px; max-width: 600px`

## 8. Performance
- Only keep active +/- 2 Plyr instances
- `loading="lazy"` + `preload="none"` on video
- HLS buffer cap: 30 seconds
- 6 renderers (by category), not 68

## 9. Library Versions
| Library | Version | Purpose |
|---------|---------|---------|
| Swiper | 11.x | Carousel |
| Plyr | 3.7.x | Video/audio player |
| hls.js | 1.5.x | HLS streaming for Azure Media Services |
