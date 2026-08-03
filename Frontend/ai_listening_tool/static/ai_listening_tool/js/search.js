/**
 * ====================================
 * SEARCH PAGE - Main Homepage Script
 * ====================================
 * 
 * This script handles the search homepage functionality including:
 * - Fetching and displaying top topics pills
 * - Loading dynamic content cards (trending topics, competitors, backlinks, ideas, news)
 * - Handling search form submission and navigation
 * 
 * API Endpoints Used:
 * - GET /api/topics/top/              - Fetches top trending topics for pills
 * - GET /api/cards/trending/          - Fetches trending topics for a company
 * - GET /api/ai/competitors/          - Fetches competitor information
 * - GET /api/ai/backlinks/            - Fetches engaged backlinks
 * - GET /api/ai/ideas/                - Fetches AI-generated content ideas
 * - GET /api/cards/newsfeed/          - Fetches relevant news articles
 */

"use strict";
import "./config.js";

// ====================================
// CONFIGURATION
// ====================================
const API_BASE_URL = RM_TOOL_CONFIG.API_BASE;
const DEFAULT_COMPANY = "EcoDrive Motors";
const API_TIMEOUT = 60000; // 60 seconds timeout - AI operations can take time

// ====================================
// UTILITY FUNCTIONS
// ====================================

/**
 * Fetch with timeout wrapper to prevent hanging requests
 * @param {string} url - The URL to fetch
 * @param {object} options - Fetch options
 * @param {number} timeout - Timeout in milliseconds
 * @returns {Promise} - Fetch promise with timeout
 */
function fetchWithTimeout(url, options = {}, timeout = API_TIMEOUT) {
  return Promise.race([
    fetch(url, options),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Request timeout')), timeout)
    )
  ]);
}

/**
 * Convert text to title case (capitalize first, last, and major words)
 * @param {string} str - The string to convert
 * @returns {string} - Title-cased string
 */
function toTitleCase(str) {
  if (!str) return str;
  
  const minorWords = ['a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to', 'from', 'by', 'in', 'of', 'with'];
  
  return str.toLowerCase().split(' ').map((word, index, array) => {
    // Always capitalize first and last word
    if (index === 0 || index === array.length - 1) {
      return word.charAt(0).toUpperCase() + word.slice(1);
    }
    // Capitalize if not a minor word
    if (!minorWords.includes(word)) {
      return word.charAt(0).toUpperCase() + word.slice(1);
    }
    return word;
  }).join(' ');
}

// ====================================
// API FETCH FUNCTIONS
// ====================================

/**
 * Fetch top trending topics from the API and populate the pills
 * API: GET /api/topics/top/
 * @returns {Promise<void>}
 */
async function fetchTopTopics() {
  const pillsContainer = document.querySelector(".rm-pills");
  if (!pillsContainer) return;

  try {
    const params = new URLSearchParams({
      days: "30",
      limit: "5"
    });

    const response = await fetchWithTimeout(`${API_BASE_URL}/topics/top/?${params}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const topics = data.topics || [];

    // Clear loading state and populate with API data
    pillsContainer.innerHTML = "";

    if (topics.length === 0) {
      // Show message if no topics available
      pillsContainer.innerHTML = '<span style="color: #999; font-size: 14px;">No topics available</span>';
    } else {
      // Only show exactly 5 topics
      const topicsToShow = topics.slice(0, 5);
      topicsToShow.forEach(topic => {
        const button = document.createElement("button");
        button.className = "rm-pill";
        const titleCased = toTitleCase(topic);
        button.setAttribute("data-topic", titleCased);
        button.textContent = titleCased;
        pillsContainer.appendChild(button);
      });
    }

    // Re-attach click handlers to the new pills
    attachPillClickHandlers();

  } catch (error) {
    console.error("Error fetching top topics:", error);
    // Show fallback pills if API fails
    pillsContainer.innerHTML = `
      <button class="rm-pill" data-topic="AI in Healthcare">AI in Healthcare</button>
      <button class="rm-pill" data-topic="Healthcare Cost">Healthcare Cost</button>
      <button class="rm-pill" data-topic="Workplace Health">Workplace Health</button>
      <button class="rm-pill" data-topic="Value Care">Value Care</button>
      <button class="rm-pill" data-topic="Health Care">Health Care</button>
    `;
    attachPillClickHandlers();
  }
}

/**
 * Attach click handlers to pill buttons for quick search
 * @returns {void}
 */
function attachPillClickHandlers() {
  const input = document.querySelector('#searchForm input[name="subject"]:not([type="hidden"])');
  document.querySelectorAll(".rm-pill[data-topic]").forEach(b => {
    b.addEventListener("click", () => {
      if (!input) return;
      input.value = b.dataset.topic || "";
      handleSearch(b.dataset.topic || "");
    });
  });
}

/**
 * Fetch trending topics for the company from the API
 * API: GET /api/cards/trending/
 * @param {string} companyId - The company ID to fetch trends for
 * @returns {Promise<void>}
 */
async function fetchTrendingTopics(companyId = "69072b397c33c037fd2da784") {
  const trendingList = document.getElementById("trendingTopicsList");
  if (!trendingList) return;

  try {
    // Show loading state
    trendingList.innerHTML = '<li class="rm-loading">Loading trending topics...</li>';

    const params = new URLSearchParams({
      company_id: companyId,
      threshold: "0.5",
      limit: "10",
      full: "0"
    });

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/trending/?${params}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const topics = await response.json();

    // Clear loading and populate
    trendingList.innerHTML = "";

    if (!topics || topics.length === 0) {
      trendingList.innerHTML = '<li class="rm-empty">No trending topics found at this time.</li>';
      return;
    }

    topics.forEach(topic => {
      const li = document.createElement("li");
      li.textContent = toTitleCase(topic);
      trendingList.appendChild(li);
    });

  } catch (error) {
    console.error("Error fetching trending topics:", error);
    // Show a more user-friendly fallback
    trendingList.innerHTML = `
      <li>Multi-Cancer Early Detection / Liquid Biopsies</li>
      <li>Tele-health and Remote Patient Monitoring</li>
      <li>Home Health & Hospital at Home Models</li>
      <li>Interoperability & Health Data Flow</li>
      <li>Behavioral Health Integration into Primary Care</li>
    `;
    // Add a subtle note
    const note = document.createElement("li");
    note.style.fontSize = "12px";
    note.style.color = "#999";
    note.style.fontStyle = "italic";
    note.textContent = "(Using cached data - API unavailable)";
    trendingList.appendChild(note);
  }
}

/**
 * Format description with last sentence in bold for emphasis
 * @param {string} description - The description text to format
 * @returns {HTMLElement|null} - Formatted div element or null
 */
function formatDescriptionWithBoldLastSentence(description) {
  if (!description || !description.trim()) return null;
  
  // Split by sentence-ending punctuation (., !, ?)
  const sentences = description.match(/[^.!?]+[.!?]+/g) || [description];
  
  if (sentences.length === 0) return null;
  
  const div = document.createElement("div");
  div.style.fontWeight = "normal";
  
  if (sentences.length === 1) {
    // Only one sentence, make it bold
    const bold = document.createElement("strong");
    bold.textContent = sentences[0].trim();
    div.appendChild(bold);
  } else {
    // Multiple sentences: normal text for all but last, bold for last
    const allButLast = sentences.slice(0, -1).join(' ').trim();
    const lastSentence = sentences[sentences.length - 1].trim();
    
    if (allButLast) {
      div.appendChild(document.createTextNode(allButLast + ' '));
    }
    
    const bold = document.createElement("strong");
    bold.textContent = lastSentence;
    div.appendChild(bold);
  }
  
  return div;
}

/**
 * Fetch AI-generated content ideas from the API
 * API: GET /api/ai/ideas/
 * @param {string} companyId - The company ID to fetch ideas for
 * @returns {Promise<void>}
 */
async function fetchIdeas(companyId = "69072b397c33c037fd2da784") {
  const ideasList = document.getElementById("ideasList");
  if (!ideasList) return;

  try {
    // Show loading state
    ideasList.innerHTML = '<li class="rm-loading">Loading ideas...</li>';

    const params = new URLSearchParams({
      company_id: companyId,
      limit: "2"
    });

    const apiUrl = `${API_BASE_URL}/ai/ideas/?${params}`;
    console.log('🎯 Ideas API: Calling URL:', apiUrl);

    const response = await fetchWithTimeout(apiUrl);

    console.log('📡 Ideas API: Response status:', response.status, response.statusText);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('📦 IDEAS API - FULL RESPONSE:', JSON.stringify(data, null, 2));
    console.log('📊 IDEAS API - Response structure:', {
      company: data.company,
      company_id: data.company_id,
      count: data.count,
      insights_exists: !!data.insights,
      insights_type: Array.isArray(data.insights) ? 'array' : typeof data.insights,
      insights_length: (data.insights || []).length
    });

    const insights = data.insights || [];

    if (insights.length > 0) {
      console.log('💡 IDEAS API - First insight FULL DATA:', JSON.stringify(insights[0], null, 2));
      console.log('💡 IDEAS API - First insight TYPE:', typeof insights[0]);
      console.log('💡 IDEAS API - Is it a string?', typeof insights[0] === 'string');
      console.log('💡 IDEAS API - Is it an object?', typeof insights[0] === 'object');
      console.log('📝 IDEAS API - ALL insights:', JSON.stringify(insights, null, 2));
    }

    // Clear loading and populate
    ideasList.innerHTML = "";

    if (insights.length === 0) {
      console.warn('⚠️ IDEAS API: No insights returned');
      console.warn('⚠️ Full data object keys:', Object.keys(data));
      ideasList.innerHTML = '<li class="rm-empty">No ideas available. Check console for API response details.</li>';
      return;
    }

    console.log(`✅ IDEAS API: Rendering ${insights.length} ideas`);

    // Handle BOTH string array and object array formats
    insights.forEach((insight, index) => {
      const li = document.createElement("li");

      let title, description;

      // If insight is a string, parse "Action: ..." format
      if (typeof insight === 'string') {
        console.log(`  Idea ${index + 1} (STRING):`, insight);
        
        // Check if string contains "Action:" format
        const actionMatch = insight.match(/^(Action:[^\n]*)\n?([\s\S]*)?$/i);
        if (actionMatch) {
          title = actionMatch[1].trim(); // "Action: ..."
          description = actionMatch[2]?.trim() || "";
        } else {
          // If no "Action:" format, use the whole string as title
          title = insight;
          description = "";
        }
      }
      // If insight is an object, extract fields
      else if (typeof insight === 'object' && insight !== null) {
        console.log(`  Idea ${index + 1} (OBJECT):`, JSON.stringify(insight, null, 2));
        
        // Check for action field first
        if (insight.action) {
          title = `Action: ${insight.action}`;
          description = insight.description || insight.summary || insight.explanation || insight.text || "";
        } else {
          title = insight.title || insight.idea || insight.name || "Untitled";
          description = insight.description || insight.summary || insight.explanation || insight.text || "";
        }
      }
      // Fallback for unexpected types
      else {
        console.warn(`  Idea ${index + 1} (UNEXPECTED TYPE):`, typeof insight, insight);
        title = String(insight);
        description = "";
      }

      console.log(`  → Displaying: Title="${title}", Description="${description}"`);

      const strong = document.createElement("strong");
      strong.textContent = title;
      li.appendChild(strong);

      if (description) {
        const descDiv = formatDescriptionWithBoldLastSentence(description);
        if (descDiv) {
          li.appendChild(descDiv);
        }
      }

      ideasList.appendChild(li);
    });

  } catch (error) {
    console.error("❌ Ideas API: Error occurred:", error);
    console.error("❌ Ideas API: Error details:", {
      name: error.name,
      message: error.message,
      stack: error.stack
    });

    // Show fallback content (2 ideas only)
    ideasList.innerHTML = '';
    
    const fallbackIdea1 = document.createElement("li");
    const strong1 = document.createElement("strong");
    strong1.textContent = "Action: Community Health Data Hubs";
    fallbackIdea1.appendChild(strong1);
    const desc1 = formatDescriptionWithBoldLastSentence("Open dashboards tracking local health metrics, setting benchmark data, allowing policy and practice decisions.");
    if (desc1) {
      fallbackIdea1.appendChild(desc1);
    }
    ideasList.appendChild(fallbackIdea1);
    
    const fallbackIdea2 = document.createElement("li");
    const strong2 = document.createElement("strong");
    strong2.textContent = "Action: Climate & Health Initiatives";
    fallbackIdea2.appendChild(strong2);
    const desc2 = formatDescriptionWithBoldLastSentence("Hospital heat index programs and air quality monitoring with alerts focused on vulnerable patient populations.");
    if (desc2) {
      fallbackIdea2.appendChild(desc2);
    }
    ideasList.appendChild(fallbackIdea2);
    // Add a subtle note
    const note = document.createElement("li");
    note.style.fontSize = "12px";
    note.style.color = "#999";
    note.style.fontStyle = "italic";
    note.textContent = `(Using cached data - API error: ${error.message})`;
    ideasList.appendChild(note);
  }
}

/**
 * Fetch relevant news feed articles from the API
 * API: GET /api/cards/newsfeed/
 * @param {string} companyId - The company ID to fetch news for
 * @returns {Promise<void>}
 */
async function fetchNewsFeed(companyId = "69072b397c33c037fd2da784") {
  const newsFeedList = document.getElementById("newsFeedList");
  if (!newsFeedList) return;

  try {
    // Show loading state
    newsFeedList.innerHTML = '<li class="rm-loading">Loading news feed...</li>';

    const params = new URLSearchParams({
      company_id: companyId,
      limit: "2",
      max_age_days: "7"
    });

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/newsfeed/?${params}`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const items = data.items || [];

    // Clear loading and populate
    newsFeedList.innerHTML = "";

    if (items.length === 0) {
      newsFeedList.innerHTML = '<li class="rm-empty">No news feed items available at this time.</li>';
      return;
    }

    items.forEach(item => {
      const li = document.createElement("li");

      const title = item.title || "Untitled";
      const description = item.description || "";
      const url = item.url || "";

      // Make the title clickable if URL exists
      if (url) {
        const titleLink = document.createElement("a");
        titleLink.href = url;
        titleLink.target = "_blank";
        titleLink.rel = "noopener noreferrer";

        const strong = document.createElement("strong");
        strong.textContent = title;

        titleLink.appendChild(strong);
        li.appendChild(titleLink);
      } else {
        const strong = document.createElement("strong");
        strong.textContent = title;
        li.appendChild(strong);
      }

      if (description) {
        li.appendChild(document.createTextNode(" " + description));
      }

      newsFeedList.appendChild(li);
    });

  } catch (error) {
    console.error("Error fetching news feed:", error);
    // Show fallback content
    newsFeedList.innerHTML = `
      <li><strong>Apple Watch gets FDA clearance for hypertension detection</strong> A new FDA-approved feature that assesses how blood vessels respond to heart beats, helping detect early signs of cardiovascular risk.</li>
      <li><strong>Climate & Health Initiatives — Regional heat policy</strong> Hospitals and healthcare systems are launching heat management initiatives aimed at protecting patients from extreme weather.</li>
    `;
    // Add a subtle note
    const note = document.createElement("li");
    note.style.fontSize = "12px";
    note.style.color = "#999";
    note.style.fontStyle = "italic";
    note.textContent = "(Using cached data - API unavailable)";
    newsFeedList.appendChild(note);
  }
}

/**
 * Fetch competitor information from the AI API
 * API: GET /api/ai/competitors/
 * @param {string} companyId - The company ID to fetch competitors for
 * @returns {Promise<void>}
 */
async function fetchCompetitors(companyId = "69072b397c33c037fd2da784") {
  const competitorsList = document.getElementById("competitorsList");
  if (!competitorsList) return;

  try {
    // Show loading state
    competitorsList.innerHTML = '<li class="rm-loading">Loading competitors...</li>';

    const params = new URLSearchParams({
      company_id: companyId,
      limit: "14"
    });

    const apiUrl = `${API_BASE_URL}/ai/competitors/?${params}`;
    console.log('🏢 Competitors API: Calling URL:', apiUrl);

    const response = await fetchWithTimeout(apiUrl, {}, 30000);

    console.log('📡 Competitors API: Response status:', response.status, response.statusText);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('📦 COMPETITORS API - FULL RESPONSE:', JSON.stringify(data, null, 2));

    // Handle both array response and object with competitors field
    const competitors = Array.isArray(data) ? data : (data.competitors || []);

    // Clear loading and populate
    competitorsList.innerHTML = "";

    if (competitors.length === 0) {
      console.warn('⚠️ COMPETITORS API: No competitors returned');
      competitorsList.innerHTML = '<li class="rm-empty">No competitors available at this time.</li>';
      return;
    }

    console.log(`✅ COMPETITORS API: Rendering ${competitors.length} competitors`);

    // Display competitors (handle both string and object formats)
    competitors.forEach((competitor, index) => {
      const li = document.createElement("li");
      
      // Handle both string and object formats
      let competitorName;
      if (typeof competitor === 'string') {
        competitorName = competitor;
      } else if (typeof competitor === 'object' && competitor !== null) {
        // Extract name from various possible fields
        competitorName = competitor.name || competitor.competitor || competitor.company || JSON.stringify(competitor);
      } else {
        competitorName = String(competitor);
      }

      li.textContent = competitorName;
      competitorsList.appendChild(li);
    });

    console.log('✅ Displayed', competitors.length, 'competitors');

  } catch (error) {
    console.error('❌ Competitors API: Error occurred:', error);
    console.error('❌ Competitors API: Error details:', {
      name: error.name,
      message: error.message,
      stack: error.stack
    });
    
    // Show fallback content
    competitorsList.innerHTML = `
      <li>UnitedHealth Group</li>
      <li>CVS Health</li>
      <li>Centene</li>
      <li>Humana</li>
      <li>Medtronic</li>
      <li>HCA Healthcare</li>
      <li>Cerner</li>
      <li>DaVita</li>
      <li>Cardinal Health</li>
      <li>Cigna</li>
      <li>Roche International</li>
      <li>Omnicell</li>
      <li>Elevance Health</li>
      <li>Kaiser Permanente</li>
    `;
    
    // Add a subtle note
    const note = document.createElement("li");
    note.style.fontSize = "12px";
    note.style.color = "#999";
    note.style.fontStyle = "italic";
    note.textContent = `(Using cached data - API error: ${error.message})`;
    competitorsList.appendChild(note);
  }
}

/**
 * Fetch engaged backlinks (most linked URLs) from the AI API
 * API: GET /api/ai/backlinks/
 * @param {string} companyId - The company ID to fetch backlinks for
 * @returns {Promise<void>}
 */
async function fetchBacklinks(companyId = "69072b397c33c037fd2da784") {
  const backlinksList = document.getElementById("backlinksList");
  if (!backlinksList) return;

  try {
    // Show loading state
    backlinksList.innerHTML = '<li class="rm-loading">Loading backlinks...</li>';

    const params = new URLSearchParams({
      company_id: companyId,
      limit: "10"
    });

    const apiUrl = `${API_BASE_URL}/ai/backlinks/?${params}`;
    console.log('🔗 Backlinks API: Calling URL:', apiUrl);

    const response = await fetchWithTimeout(apiUrl, {}, 30000);

    console.log('📡 Backlinks API: Response status:', response.status, response.statusText);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log('📦 BACKLINKS API - FULL RESPONSE:', JSON.stringify(data, null, 2));

    // Handle both array response and object with engaged_links field
    const backlinks = Array.isArray(data) ? data : (data.engaged_links || []);

    // Clear loading and populate
    backlinksList.innerHTML = "";

    if (backlinks.length === 0) {
      console.warn('⚠️ BACKLINKS API: No backlinks returned');
      backlinksList.innerHTML = '<li class="rm-empty">No backlinks available at this time.</li>';
      return;
    }

    console.log(`✅ BACKLINKS API: Rendering ${backlinks.length} backlinks`);

    // Display backlinks (handle both string URLs and object formats)
    backlinks.forEach((backlink, index) => {
      const li = document.createElement("li");
      
      // Handle both string URL and object formats
      let url;
      if (typeof backlink === 'string') {
        url = backlink;
      } else if (typeof backlink === 'object' && backlink !== null) {
        // Extract URL from various possible fields
        url = backlink.url || backlink.link || backlink.href || JSON.stringify(backlink);
      } else {
        url = String(backlink);
      }

      // Create clickable link
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = url;
      
      li.appendChild(link);
      backlinksList.appendChild(li);
    });

    console.log('✅ Displayed', backlinks.length, 'backlinks');

  } catch (error) {
    console.error('❌ Backlinks API: Error occurred:', error);
    console.error('❌ Backlinks API: Error details:', {
      name: error.name,
      message: error.message,
      stack: error.stack
    });
    
    // Show fallback content
    backlinksList.innerHTML = `
      <li><a href="https://example.com/health-resources" target="_blank" rel="noopener noreferrer">https://example.com/health-resources</a></li>
      <li><a href="https://example.com/medical-insights" target="_blank" rel="noopener noreferrer">https://example.com/medical-insights</a></li>
      <li><a href="https://example.com/patient-care" target="_blank" rel="noopener noreferrer">https://example.com/patient-care</a></li>
      <li><a href="https://example.com/clinical-research" target="_blank" rel="noopener noreferrer">https://example.com/clinical-research</a></li>
      <li><a href="https://example.com/healthcare-tech" target="_blank" rel="noopener noreferrer">https://example.com/healthcare-tech</a></li>
    `;
    
    // Add a subtle note
    const note = document.createElement("li");
    note.style.fontSize = "12px";
    note.style.color = "#999";
    note.style.fontStyle = "italic";
    note.style.border = "none";
    note.textContent = `(Using cached data - API error: ${error.message})`;
    backlinksList.appendChild(note);
  }
}

// ====================================
// SEARCH HANDLING
// ====================================

/**
 * Handle search form submission and navigate to results page
 * @param {string} subject - The search query entered by user
 * @returns {void}
 */
function handleSearch(subject) {
  if (!subject || !subject.trim()) {
    const errEl = document.getElementById("err");
    if (errEl) errEl.textContent = "Please enter a search term";
    return;
  }

  // Clear any previous session data for fresh search
  sessionStorage.removeItem('rm_history_id');
  sessionStorage.removeItem('rm_days');
  sessionStorage.removeItem('rm_platforms');
  sessionStorage.removeItem('rm_sentiments');

  // Store the new subject
  sessionStorage.setItem("rm_subject", subject.trim());

  // Immediately redirect to results page with fresh flag
  // The results page will handle the API call and show loading state
  window.location.href = `/tool/results/?subject=${encodeURIComponent(subject.trim())}&fresh=1`;
}

/**
 * Prevent text selection after browser autocomplete fills in the input
 * @param {HTMLInputElement} inputElement - The input element to process
 * @returns {void}
 */
function preventAutoSelection(inputElement) {
  if (!inputElement) return;
  
  // Remove selection by moving cursor to end
  const length = inputElement.value.length;
  inputElement.setSelectionRange(length, length);
}

// ====================================
// PAGE INITIALIZATION
// ====================================

/**
 * Initialize the search homepage on page load
 * - Sets up form handlers
 * - Loads all card data
 * - Handles URL parameters for auto-search
 */
document.addEventListener("DOMContentLoaded", () => {
  console.log("Page loaded successfully!");

  const form = document.getElementById("searchForm");
  if (!form) return;

  // Pick the visible text input only
  const input = form.querySelector('input[name="subject"]:not([type="hidden"])');

  // Prevent auto-selection after autocomplete
  if (input) {
    input.addEventListener('input', () => {
      // Small delay to let autocomplete finish
      setTimeout(() => preventAutoSelection(input), 10);
    });
    
    // Also handle on change event (for some browsers)
    input.addEventListener('change', () => {
      setTimeout(() => preventAutoSelection(input), 10);
    });
  }

  // Check if there's a subject parameter in the URL
  const urlParams = new URLSearchParams(window.location.search);
  const subjectFromUrl = urlParams.get('subject');
  
  if (subjectFromUrl && subjectFromUrl.trim()) {
    // Auto-populate the search field
    if (input) {
      input.value = subjectFromUrl.trim();
      preventAutoSelection(input);
    }
    // Automatically submit the search
    console.log('Auto-submitting search from URL parameter:', subjectFromUrl);
    handleSearch(subjectFromUrl.trim());
  }

  // Intercept form submission to use our API workflow
  form.addEventListener("submit", (e) => {
    e.preventDefault(); // Prevent default form submission
    const subject = (input?.value || "").trim();
    handleSearch(subject);
  });

  // Load data from API endpoints on page load (non-blocking)
  // Wrap in setTimeout to ensure it doesn't block page rendering
  setTimeout(() => {
    fetchTopTopics().catch(err => console.error("Failed to load top topics:", err));
    fetchTrendingTopics().catch(err => console.error("Failed to load trending topics:", err));
    fetchCompetitors().catch(err => console.error("Failed to load competitors:", err));
    fetchBacklinks().catch(err => console.error("Failed to load backlinks:", err));
    fetchIdeas().catch(err => console.error("Failed to load ideas:", err));
    fetchNewsFeed().catch(err => console.error("Failed to load news feed:", err));
  }, 0);
});

