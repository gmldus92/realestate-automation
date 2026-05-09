"""카카오맵 기반 매물 위치 지도 HTML 생성"""
from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawlers.naver_land import Listing

KAKAO_MAP_KEY = os.environ.get("KAKAO_MAP_KEY", "")


def build_map_html(listings: list["Listing"]) -> str:
    markers_js = []
    for l in listings:
        label = f"{'🚨급매 ' if l.is_urgent else ''}{'🆕 ' if l.is_new else ''}{l.name}"
        color = "#e74c3c" if l.is_urgent else ("#3498db" if l.is_new else "#2ecc71")
        info = (
            f"{l.name}\\n"
            f"{l.price // 10000}억{l.price % 10000:,}만원\\n"
            f"{l.area_pyeong}평 / {l.floor}층\\n"
            f"{l.address}"
        )
        markers_js.append(
            f'addMarker("{l.address}", "{label}", "{info}", "{color}", "{l.url}");'
        )

    markers_str = "\n      ".join(markers_js)

    return f"""
<div id="map" style="width:100%;height:400px;border-radius:12px;"></div>
<script type="text/javascript"
  src="//dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_MAP_KEY}&libraries=services">
</script>
<script>
  var mapContainer = document.getElementById('map');
  var mapOption = {{
    center: new kakao.maps.LatLng(37.4900, 126.9800),
    level: 9
  }};
  var map = new kakao.maps.Map(mapContainer, mapOption);
  var geocoder = new kakao.maps.services.Geocoder();
  var infowindow = new kakao.maps.InfoWindow({{zIndex:1}});

  function addMarker(address, title, content, color, url) {{
    geocoder.addressSearch(address, function(result, status) {{
      if (status !== kakao.maps.services.Status.OK) return;
      var coords = new kakao.maps.LatLng(result[0].y, result[0].x);
      var marker = new kakao.maps.Marker({{ map: map, position: coords, title: title }});
      kakao.maps.event.addListener(marker, 'click', function() {{
        infowindow.setContent(
          '<div style="padding:8px;font-size:13px;max-width:200px;">' +
          '<strong>' + title + '</strong><br>' +
          content.replace(/\\n/g,'<br>') +
          '<br><a href="' + url + '" target="_blank" style="color:#3498db;">매물 보기</a>' +
          '</div>'
        );
        infowindow.open(map, marker);
      }});
    }});
  }}

  {markers_str}
</script>
"""
