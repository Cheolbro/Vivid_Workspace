/**
 * Node V5 — API Fetch & Result Handler (n8n Code Node)
 *
 * 목적: Pexels/Pixabay API HTTP 요청을 n8n Code 노드 내에서 직접 수행합니다.
 *       기본 HTTP Request 노드가 기존 item 데이터를 덮어쓰는(Data Loss) 문제를 해결합니다.
 *       기존 메타데이터(chapter_id, scene_id, z_index 등)를 100% 보존하면서
 *       api_asset_path, api_asset_type 필드만 추가하여 다음 노드로 넘깁니다.
 */

const item = $input.item.json;

if (item.source_api === 'pexels') {
  const options = {
    method: 'GET',
    url: 'https://api.pexels.com/videos/search',
    qs: {
      query: item.search_query,
      per_page: 1,
      size: 'large',
      orientation: 'landscape'
    },
    headers: {
      'Authorization': $env.PEXELS_API_KEY
    },
    json: true
  };
  try {
    const response = await this.helpers.httpRequest(options);
    const videos = response.videos || [];
    if (videos.length > 0 && videos[0].video_files) {
      const hd = videos[0].video_files.find(f => f.quality === 'hd' && f.width >= 1920) || videos[0].video_files[0];
      return { json: { ...item, api_asset_path: hd.link, api_asset_type: 'video', api_success: true } };
    }
  } catch(e) {
    console.error('Pexels API Error:', e.message);
  }
} else if (item.source_api === 'pixabay') {
  const options = {
    method: 'GET',
    url: 'https://pixabay.com/api/',
    qs: {
      key: $env.PIXABAY_API_KEY,
      q: item.search_query,
      per_page: 3,
      image_type: 'photo',
      orientation: 'horizontal',
      min_width: 1920,
      safesearch: 'true'
    },
    json: true
  };
  try {
    const response = await this.helpers.httpRequest(options);
    const hits = response.hits || [];
    if (hits.length > 0) {
      return { json: { ...item, api_asset_path: hits[0].largeImageURL, api_asset_type: 'image', api_success: true } };
    }
  } catch(e) {
    console.error('Pixabay API Error:', e.message);
  }
}

// 폴백: 검색 결과 0건 또는 에러 시 solid_color 강제 전환
console.warn(`[V5 API] 검색 결과 0건 또는 에러 (query=${item.search_query}), solid_color 폴백`);
return { json: { ...item, bg_style: 'solid_color', source_api: null, api_asset_path: null, api_success: false } };
