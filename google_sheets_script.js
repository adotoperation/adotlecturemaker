/**
 * =========================================================================
 * 에이닷 내신자료 메이커 (A. WEAVE) - Google Sheets 연동 백엔드 스크립트
 * =========================================================================
 * 
 * [스프레드시트 열(Column) 구성 - 7열 체계]
 * - A열(1): 분류 (material_type / label: 모의고사, 부교재, 교과서, 자체제작 등)
 * - B열(2): 유형 (doc_type: 강의용교안, 단어TEST, 9종변형문제)
 * - C열(3): 제목 (title: 예 - 26년 고3 9월 모의고사 31번)
 * - D열(4): 문장데이터 (sentence_pairs JSON 문자열)
 * - E열(5): 분석데이터 (analysis_data JSON 문자열 - 순수 텍스트 구문분석 데이터)
 * - F열(6): 삽화데이터 (illustration_url - 지문 삽화 Base64 또는 이미지 URL 단독 저장)
 * - G열(7): 저장일시 및 지점 (timestamp 및 branch)
 * 
 * [설치 및 배포 방법]
 * 1. 교안이 저장되는 구글 스프레드시트 접속
 * 2. 상단 메뉴 [확장 프로그램] -> [Apps Script] 클릭
 * 3. 기존 코드를 모두 지우고 본 스크립트 전체를 복사하여 붙여넣기
 * 4. 상단 [저장 (Ctrl+S)] 클릭 후 우측 상단 [배포] -> [새 배포] 클릭
 * 5. 유형: '웹 앱' 선택
 *    - 설명: "F열 삽화 분리 저장 적용"
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
  return createJsonResponse({ status: "ok", message: "A.WEAVE Google Sheets API is running." });
}

// -------------------------------------------------------------------------
// 1. SAVE (자료 저장 - F열 삽화 데이터 독립 저장)
// -------------------------------------------------------------------------
function handleSave(ss, data) {
  var sheetName = data.material_type || data.label || "모의고사";
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    sheet.appendRow(["분류", "유형", "제목", "문장데이터", "분석데이터", "삽화데이터", "저장일시"]);
  }

  var title = (data.title || "").trim();
  var docType = (data.doc_type || "강의용교안").trim();
  var materialType = (data.material_type || sheetName).trim();
  var sentencePairsStr = JSON.stringify(data.sentence_pairs || []);
  
  // E열 분석데이터: 삽화 데이터는 분리하므로 analysis_data 내부의 illustration_url은 제거
  var analysisDataObj = data.analysis_data || {};
  if (typeof analysisDataObj === "string") {
    try { analysisDataObj = JSON.parse(analysisDataObj); } catch(e) {}
  }
  delete analysisDataObj.illustration_url;
  if (analysisDataObj.summary_info && typeof analysisDataObj.summary_info === "object") {
    analysisDataObj.summary_info.illustration_url = "";
  }
  var analysisDataStr = JSON.stringify(analysisDataObj);

  // F열: 삽화 데이터 (Base64 또는 URL)
  var illustrationUrl = (data.illustration_url || "").trim();
  if (!illustrationUrl && data.branch && (String(data.branch).startsWith("data:image/") || String(data.branch).startsWith("http"))) {
    illustrationUrl = String(data.branch).trim();
  }
  
  // G열: 지점 및 타임스탬프
  var branch = (data.branch || "본사").trim();
  if (branch.startsWith("data:image/") || branch.startsWith("http")) {
    branch = "본사";
  }
  var nowIso = new Date().toISOString();
  var timestampStr = branch ? (branch + " | " + nowIso) : nowIso;

  // 기존 행 탐색 (제목과 유형이 일치하는 행 갱신)
  var lastRow = sheet.getLastRow();
  var targetRow = -1;

  if (lastRow >= 2) {
    var range = sheet.getRange(2, 1, lastRow - 1, 3);
    var values = range.getValues();
    for (var i = 0; i < values.length; i++) {
      var rowTitle = String(values[i][2]).trim();
      var rowDocType = String(values[i][1]).trim();
      if (rowTitle === title && (!docType || rowDocType === docType)) {
        targetRow = i + 2;
        break;
      }
    }
  }

  var rowValues = [
    materialType,        // A열: 분류
    docType,             // B열: 유형
    title,               // C열: 제목
    sentencePairsStr,    // D열: 문장데이터
    analysisDataStr,     // E열: 분석데이터 (순수 텍스트)
    illustrationUrl,     // F열: 삽화데이터 (독립 저장)
    timestampStr         // G열: 지점/일시
  ];

  if (targetRow > 0) {
    sheet.getRange(targetRow, 1, 1, rowValues.length).setValues([rowValues]);
  } else {
    sheet.appendRow(rowValues);
  }

  SpreadsheetApp.flush();
  return createJsonResponse({
    success: true,
    title: title,
    material_type: materialType,
    doc_type: docType,
    has_illustration: Boolean(illustrationUrl)
  });
}

// -------------------------------------------------------------------------
// 2. LOAD (자료 불러오기 - E열 분석데이터 + F열 삽화데이터 결합 반환)
// -------------------------------------------------------------------------
function handleLoad(ss, data) {
  var title = (data.title || "").trim();
  var docType = (data.doc_type || "").trim();
  var sheetName = data.material_type || data.label || "";

  var sheetsToSearch = [];
  if (sheetName && ss.getSheetByName(sheetName)) {
    sheetsToSearch.push(ss.getSheetByName(sheetName));
  } else {
    sheetsToSearch = ss.getSheets();
  }

  for (var s = 0; s < sheetsToSearch.length; s++) {
    var sheet = sheetsToSearch[s];
    var sName = sheet.getName();
    if (sName.startsWith("RDB_")) continue; // 시스템 시트 제외

    var lastRow = sheet.getLastRow();
    if (lastRow < 2) continue;

    var numCols = Math.min(sheet.getLastColumn(), 7);
    var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    for (var i = 0; i < values.length; i++) {
      var row = values[i];
      var rowTitle = String(row[2]).trim();
      var rowDocType = String(row[1]).trim();

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

        var branchMeta = (numCols >= 7 && row[6]) ? String(row[6]).trim() : "본사";
        var branchName = branchMeta.split("|")[0].trim() || "본사";
        if (branchName.startsWith("data:image/") || branchName.startsWith("http")) {
          branchName = "본사";
        }

        return createJsonResponse({
          success: true,
          title: rowTitle,
          material_type: String(row[0]).trim() || sName,
          doc_type: rowDocType,
          label: String(row[0]).trim() || sName,
          sentence_pairs: sentencePairs,
          analysis_data: analysisData,
          illustration_url: illustrationUrl,
          branch: branchName
        });
      }
    }
  }

  return createJsonResponse({ success: false, error: "저장된 자료를 찾을 수 없습니다: " + title });
}

// -------------------------------------------------------------------------
// 3. LIST (목록 조회 - F열 삽화 여부 포함)
// -------------------------------------------------------------------------
function handleList(ss, data) {
  var saves = [];
  var sheets = ss.getSheets();

  for (var s = 0; s < sheets.length; s++) {
    var sheet = sheets[s];
    var sName = sheet.getName();
    if (sName.startsWith("RDB_")) continue;

    var lastRow = sheet.getLastRow();
    if (lastRow < 2) continue;

    var numCols = Math.min(sheet.getLastColumn(), 7);
    var values = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    for (var i = 0; i < values.length; i++) {
      var row = values[i];
      var matType = String(row[0]).trim() || sName;
      var docType = String(row[1]).trim() || "강의용교안";
      var title = String(row[2]).trim();
      if (!title) continue;

      var illuUrl = (numCols >= 6 && row[5]) ? String(row[5]).trim() : "";
      if (illuUrl && !illuUrl.startsWith("data:image/") && !illuUrl.startsWith("http")) {
        illuUrl = "";
      }
      var branchMeta = (numCols >= 7 && row[6]) ? String(row[6]).trim() : "본사";
      var branchName = branchMeta.split("|")[0].trim() || "본사";
      if (branchName.startsWith("data:image/") || branchName.startsWith("http")) {
        branchName = "본사";
      }

      saves.push({
        filename: title + ".json",
        title: title,
        material_type: matType,
        doc_type: docType,
        label: matType,
        branch: branchName,
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
  var sheetName = data.material_type || data.label || "";

  var sheetsToSearch = sheetName && ss.getSheetByName(sheetName) ? [ss.getSheetByName(sheetName)] : ss.getSheets();
  var deleted = false;

  for (var s = 0; s < sheetsToSearch.length; s++) {
    var sheet = sheetsToSearch[s];
    if (sheet.getName().startsWith("RDB_")) continue;

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
    data.branch || "본사",
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
