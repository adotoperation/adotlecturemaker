/**
 * =========================================================================
 * 에이닷 내신자료 메이커 (A. WEAVE) - Google Sheets 연동 백엔드 스크립트
 * =========================================================================
 * 
 * [스프레드시트 시트(워크시트) 명]
 * - RDB_교안 (또는 RDB_ 교안): 전체 교안 통합 저장 워크시트
 * - RDB_로그: 토큰 사용량 감사 로그
 * - RDB_아이디: 지점 계정 관리 시트
 * 
 * [스프레드시트 열(Column) 구성 - 8열 표준 데이터셋]
 * - A열(1): 분류 (material_type: 모의고사, 부교재, 교과서, 기타 등)
 * - B열(2): 유형 (doc_type: 강의용교안, 단어TEST, 9종변형문제)
 * - C열(3): 제목 (title: 예 - 26년 고3 9월 모의고사 31번)
 * - D열(4): 문장데이터 (sentence_pairs JSON 문자열)
 * - E열(5): 분석데이터 (analysis_data JSON 문자열 - 순수 텍스트 구문분석 데이터)
 * - F열(6): 삽화데이터 (illustration_url - 지문 삽화 Base64 또는 이미지 URL 단독 저장)
 * - G열(7): 저장일시 (timestamp)
 * - H열(8): 아이디 (username / branch: 본사, 강남 등)
 * 
 * [설치 및 배포 방법]
 * 1. 교안이 저장되는 구글 스프레드시트 접속
 * 2. 상단 메뉴 [확장 프로그램] -> [Apps Script] 클릭
 * 3. 기존 코드를 모두 지우고 본 스크립트 전체를 복사하여 붙여넣기
 * 4. 상단 [저장 (Ctrl+S)] 클릭 후 우측 상단 [배포] -> [새 배포] 클릭
 * 5. 유형: '웹 앱' 선택
 *    - 설명: "RDB_교안 8열 데이터셋 저장 적용 (삽화 F열 / 아이디 H열)"
 *    - 다음 사용자 권한으로 실행: '나(내 계정)'
 *    - 액세스 권한이 있는 사용자: '모든 사용자(Anyone)'
 * 6. [배포] 클릭 후 승인 완료
 */

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000); // 30초 대기
  } catch (err) {
    return createJsonResponse({ success: false, error: "서버가 혼잡합니다. 잠시 후 다시 시도해 주세요." });
  }

  try {
    if (!e || !e.postData || !e.postData.contents) {
      return createJsonResponse({ success: false, error: "요청 본문이 비어 있습니다." });
    }

    var data = JSON.parse(e.postData.contents);
    var action = data.action;
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    if (action === "save") {
      return handleSave(ss, data);
    } else if (action === "load") {
      return handleLoad(ss, data);
    } else if (action === "list") {
      return handleList(ss, data);
    } else if (action === "delete") {
      return handleDelete(ss, data);
    } else if (action === "log") {
      return handleLog(ss, data);
    } else if (action === "login") {
      return handleLogin(ss, data);
    } else {
      return createJsonResponse({ success: false, error: "알 수 없는 작업(action): " + action });
    }
  } catch (globalErr) {
    return createJsonResponse({ success: false, error: globalErr.toString() });
  } finally {
    try { lock.releaseLock(); } catch(e) {}
  }
}

function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheetNames = ss.getSheets().map(function(s) { return s.getName(); });
  return createJsonResponse({
    status: "ok",
    message: "A.WEAVE Google Sheets API is running.",
    sheets: sheetNames
  });
}

/**
 * RDB_교안 (또는 RDB_ 교안) 전용 워크시트 반환 함수
 */
function getHandoutSheet(ss) {
  var sheet = ss.getSheetByName("RDB_교안") || ss.getSheetByName("RDB_ 교안");
  if (!sheet) {
    sheet = ss.insertSheet("RDB_교안");
    sheet.appendRow(["분류", "유형", "제목", "문장데이터", "분석데이터", "삽화데이터", "저장일시", "아이디"]);
  }
  return sheet;
}

// -------------------------------------------------------------------------
// 1. SAVE (자료 저장 - RDB_교안 8열 표준 데이터셋)
// -------------------------------------------------------------------------
function handleSave(ss, data) {
  var sheet = getHandoutSheet(ss);

  // 헤더가 비어있을 경우 표준 8열 헤더 작성
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(["분류", "유형", "제목", "문장데이터", "분석데이터", "삽화데이터", "저장일시", "아이디"]);
  }

  var title = (data.title || "").trim();
  var docType = (data.doc_type || "강의용교안").trim();
  var materialType = (data.material_type || data.label || "모의고사").trim();
  var sentencePairsStr = JSON.stringify(data.sentence_pairs || []);
  
  // E열 분석데이터: 삽화 데이터는 F열로 분리하므로 analysis_data 내부의 illustration_url은 제거
  var analysisDataObj = data.analysis_data || {};
  if (typeof analysisDataObj === "string") {
    try { analysisDataObj = JSON.parse(analysisDataObj); } catch(e) {}
  }
  delete analysisDataObj.illustration_url;
  if (analysisDataObj.summary_info && typeof analysisDataObj.summary_info === "object") {
    analysisDataObj.summary_info.illustration_url = "";
  }
  var analysisDataStr = JSON.stringify(analysisDataObj);

  // F열: 삽화데이터 (Base64 또는 URL)
  var illustrationUrl = (data.illustration_url || "").trim();
  if (!illustrationUrl && data.branch && (String(data.branch).startsWith("data:image/") || String(data.branch).startsWith("http"))) {
    illustrationUrl = String(data.branch).trim();
  }
  
  // G열: 저장일시
  var nowIso = new Date().toISOString();
  var timestampStr = data.timestamp || nowIso;

  // H열: 아이디 (지점 또는 사용자 ID)
  var userId = (data.username || data.branch || "본사").trim();
  if (userId.startsWith("data:image/") || userId.startsWith("http")) {
    userId = "본사";
  }

  // 기존 행 탐색 (제목과 유형이 일치하는 행 갱신)
  var lastRow = sheet.getLastRow();
  var targetRow = -1;

  if (lastRow >= 2) {
    var range = sheet.getRange(2, 2, lastRow - 1, 2); // B열(유형), C열(제목)
    var values = range.getValues();
    for (var i = 0; i < values.length; i++) {
      var rowDocType = String(values[i][0]).trim();
      var rowTitle = String(values[i][1]).trim();
      if (rowTitle === title && (!docType || rowDocType === docType)) {
        targetRow = i + 2;
        break;
      }
    }
  }

  var rowValues = [
    materialType,        // 1. 분류
    docType,             // 2. 유형
    title,               // 3. 제목
    sentencePairsStr,    // 4. 문장데이터
    analysisDataStr,     // 5. 분석데이터
    illustrationUrl,     // 6. 삽화데이터
    timestampStr,        // 7. 저장일시
    userId               // 8. 아이디
  ];

  if (targetRow > 0) {
    sheet.getRange(targetRow, 1, 1, rowValues.length).setValues([rowValues]);
  } else {
    sheet.appendRow(rowValues);
  }

  SpreadsheetApp.flush();
  return createJsonResponse({
    success: true,
    sheet_name: sheet.getName(),
    title: title,
    material_type: materialType,
    doc_type: docType,
    has_illustration: Boolean(illustrationUrl)
  });
}

// -------------------------------------------------------------------------
// 2. LOAD (자료 불러오기 - RDB_교안 우선 조회 및 하위 호환)
// -------------------------------------------------------------------------
function handleLoad(ss, data) {
  var title = (data.title || "").trim();
  var docType = (data.doc_type || "").trim();
  var sheetName = data.material_type || data.label || "";

  // 1순위: RDB_교안 (또는 RDB_ 교안)
  var targetSheet = ss.getSheetByName("RDB_교안") || ss.getSheetByName("RDB_ 교안");
  var sheetsToSearch = [];
  if (targetSheet) {
    sheetsToSearch.push(targetSheet);
  }

  // 2순위: 지정 시트 또는 전체 시트 하위 호환 탐색
  if (sheetName && ss.getSheetByName(sheetName) && ss.getSheetByName(sheetName) !== targetSheet) {
    sheetsToSearch.push(ss.getSheetByName(sheetName));
  }
  var allSheets = ss.getSheets();
  for (var k = 0; k < allSheets.length; k++) {
    var sObj = allSheets[k];
    var sName = sObj.getName();
    if (sObj !== targetSheet && !sName.startsWith("RDB_로그") && !sName.startsWith("RDB_아이디") && sheetsToSearch.indexOf(sObj) === -1) {
      sheetsToSearch.push(sObj);
    }
  }

  for (var s = 0; s < sheetsToSearch.length; s++) {
    var sheet = sheetsToSearch[s];
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) continue;

    var numCols = Math.min(sheet.getLastColumn(), 8);
    var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    for (var i = 0; i < values.length; i++) {
      var row = values[i];
      var rowMatType = String(row[0]).trim();
      var rowDocType = String(row[1]).trim();
      var rowTitle = String(row[2]).trim();

      if (rowTitle === title && (!docType || rowDocType === docType)) {
        var sentencePairs = [];
        try { sentencePairs = JSON.parse(row[3]); } catch(e) {}

        var analysisData = {};
        try { analysisData = JSON.parse(row[4]); } catch(e) {}

        // F열(6번째 열)에서 삽화 데이터 추출
        var illustrationUrl = (numCols >= 6 && row[5]) ? String(row[5]).trim() : "";
        if (illustrationUrl && !illustrationUrl.startsWith("data:image/") && !illustrationUrl.startsWith("http")) {
          illustrationUrl = "";
        }
        
        // 과거 데이터 하위 호환성 (과거에는 E열에 저장되었던 경우)
        if (!illustrationUrl && analysisData.illustration_url) {
          illustrationUrl = analysisData.illustration_url;
        }

        // analysisData에도 illustration_url 동기화
        analysisData.illustration_url = illustrationUrl;
        if (analysisData.summary_info && typeof analysisData.summary_info === "object") {
          analysisData.summary_info.illustration_url = illustrationUrl;
        }

        // H열(8번째 열: 아이디) 또는 G열(7번째 열: 지점/일시) 추출
        var userId = "본사";
        if (numCols >= 8 && row[7]) {
          userId = String(row[7]).trim();
        } else if (numCols >= 7 && row[6]) {
          var gCol = String(row[6]).trim();
          if (gCol.includes("|")) {
            userId = gCol.split("|")[0].trim();
          } else if (!gCol.startsWith("data:image/")) {
            userId = gCol;
          }
        }
        if (userId.startsWith("data:image/") || userId.startsWith("http")) {
          userId = "본사";
        }

        return createJsonResponse({
          success: true,
          title: rowTitle,
          material_type: rowMatType || "모의고사",
          doc_type: rowDocType || "강의용교안",
          label: rowMatType || "모의고사",
          sentence_pairs: sentencePairs,
          analysis_data: analysisData,
          illustration_url: illustrationUrl,
          branch: userId,
          username: userId
        });
      }
    }
  }

  return createJsonResponse({ success: false, error: "저장된 자료를 찾을 수 없습니다: " + title });
}

// -------------------------------------------------------------------------
// 3. LIST (목록 조회 - RDB_교안 및 전체 워크시트 조회)
// -------------------------------------------------------------------------
function handleList(ss, data) {
  var saves = [];
  var seenKeys = {};

  // 1순위: RDB_교안 (또는 RDB_ 교안)
  var targetSheet = ss.getSheetByName("RDB_교안") || ss.getSheetByName("RDB_ 교안");
  var sheetsToSearch = [];
  if (targetSheet) {
    sheetsToSearch.push(targetSheet);
  }

  // 2순위: 기타 분류별 시트 하위 호환 탐색
  var allSheets = ss.getSheets();
  for (var k = 0; k < allSheets.length; k++) {
    var sObj = allSheets[k];
    var sName = sObj.getName();
    if (sObj !== targetSheet && !sName.startsWith("RDB_로그") && !sName.startsWith("RDB_아이디") && sheetsToSearch.indexOf(sObj) === -1) {
      sheetsToSearch.push(sObj);
    }
  }

  for (var s = 0; s < sheetsToSearch.length; s++) {
    var sheet = sheetsToSearch[s];
    var sName = sheet.getName();
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) continue;

    var numCols = Math.min(sheet.getLastColumn(), 8);
    var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    for (var i = 0; i < values.length; i++) {
      var row = values[i];
      var matType = String(row[0]).trim() || (sName.startsWith("RDB_") ? "모의고사" : sName);
      var docType = String(row[1]).trim() || "강의용교안";
      var title = String(row[2]).trim();
      if (!title || title === "제목" || title === "Title") continue;

      var dedupeKey = title + "|" + docType;
      if (seenKeys[dedupeKey]) continue;
      seenKeys[dedupeKey] = true;

      var illuUrl = (numCols >= 6 && row[5]) ? String(row[5]).trim() : "";
      if (illuUrl && !illuUrl.startsWith("data:image/") && !illuUrl.startsWith("http")) {
        illuUrl = "";
      }

      var userId = "본사";
      if (numCols >= 8 && row[7]) {
        userId = String(row[7]).trim();
      } else if (numCols >= 7 && row[6]) {
        var gMeta = String(row[6]).trim();
        if (gMeta.includes("|")) {
          userId = gMeta.split("|")[0].trim();
        } else if (!gMeta.startsWith("data:image/")) {
          userId = gMeta;
        }
      }
      if (userId.startsWith("data:image/") || userId.startsWith("http")) {
        userId = "본사";
      }

      saves.push({
        filename: title + ".json",
        title: title,
        material_type: matType,
        doc_type: docType,
        label: matType,
        branch: userId,
        username: userId,
        illustration_url: illuUrl,
        has_illu: Boolean(illuUrl && !illuUrl.includes("placeholder")),
        mtime: new Date().getTime() / 1000
      });
    }
  }

  return createJsonResponse({ success: true, saves: saves });
}

// -------------------------------------------------------------------------
// 4. DELETE (자료 삭제)
// -------------------------------------------------------------------------
function handleDelete(ss, data) {
  var title = (data.title || "").trim();
  var docType = (data.doc_type || "").trim();

  var targetSheet = ss.getSheetByName("RDB_교안") || ss.getSheetByName("RDB_ 교안");
  var sheetsToSearch = [];
  if (targetSheet) {
    sheetsToSearch.push(targetSheet);
  }
  var allSheets = ss.getSheets();
  for (var k = 0; k < allSheets.length; k++) {
    var name = allSheets[k].getName();
    if (allSheets[k] !== targetSheet && !name.startsWith("RDB_로그") && !name.startsWith("RDB_아이디")) {
      sheetsToSearch.push(allSheets[k]);
    }
  }

  var deleted = false;
  for (var s = 0; s < sheetsToSearch.length; s++) {
    var sheet = sheetsToSearch[s];
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) continue;

    var values = sheet.getRange(2, 2, lastRow - 1, 2).getValues(); // B열(유형), C열(제목)
    for (var i = values.length - 1; i >= 0; i--) {
      var rowDocType = String(values[i][0]).trim();
      var rowTitle = String(values[i][1]).trim();

      if (rowTitle === title && (!docType || rowDocType === docType)) {
        sheet.deleteRow(i + 2);
        deleted = true;
      }
    }
  }

  SpreadsheetApp.flush();
  return createJsonResponse({ success: deleted });
}

// -------------------------------------------------------------------------
// 5. LOG (토큰 사용량 기록 - RDB_로그)
// -------------------------------------------------------------------------
function handleLog(ss, data) {
  var sheet = ss.getSheetByName("RDB_로그");
  if (!sheet) {
    sheet = ss.insertSheet("RDB_로그");
    sheet.appendRow(["기록일시", "지점", "분류", "유형", "제목", "토큰수", "금액(원)"]);
  }

  sheet.appendRow([
    data.timestamp || new Date().toISOString(),
    data.branch || data.username || "본사",
    data.material_type || "모의고사",
    data.doc_type || "강의용교안",
    data.title || "",
    data.tokens || 0,
    data.cost_krw || 0
  ]);

  SpreadsheetApp.flush();
  return createJsonResponse({ success: true });
}

// -------------------------------------------------------------------------
// 6. LOGIN (지점 로그인 인증 - RDB_아이디)
// -------------------------------------------------------------------------
function handleLogin(ss, data) {
  var sheet = ss.getSheetByName("RDB_아이디");
  if (!sheet) {
    return createJsonResponse({ success: true, username: data.username || "본사" });
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return createJsonResponse({ success: true, username: data.username || "본사" });
  }

  var values = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  var inputUser = String(data.username || "").trim();
  var inputPass = String(data.password || "").trim();

  for (var i = 0; i < values.length; i++) {
    var u = String(values[i][0]).trim();
    var p = String(values[i][1]).trim();
    if (u === inputUser && p === inputPass) {
      return createJsonResponse({ success: true, username: u });
    }
  }

  return createJsonResponse({ success: false, error: "아이디 또는 비밀번호가 일치하지 않습니다." });
}

// -------------------------------------------------------------------------
// Utility: JSON Response Helper
// -------------------------------------------------------------------------
function createJsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
