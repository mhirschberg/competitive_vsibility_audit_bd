"""Shared strict and fallback Google/Bing Markdown SERP parsers."""

import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

# SERVICE-ONLY-IMPORTS: start
from .brightdata_transport import BrightDataAPIError
# SERVICE-ONLY-IMPORTS: end


class SerpParserPorts:
    def __init__(
        self, *, get_hostname, get_root_domain, canonical_source_url,
        is_google_goto_url, resolve_google_goto_url, diagnostics,
    ):
        self.get_hostname = get_hostname
        self.get_root_domain = get_root_domain
        self.canonical_source_url = canonical_source_url
        self.is_google_goto_url = is_google_goto_url
        self.resolve_google_goto_url = resolve_google_goto_url
        self.diagnostics = diagnostics


MARKDOWN_RESULT_LINK_PATTERN = re.compile('\\[(?P<title>[^\\]\\n]{2,300})\\]\\((?P<url>[^)\\n]+)\\)')

DIRECT_HTTP_URL_PATTERN = re.compile('https?://[^\\s<>\'\\"\\])]+')

SERP_INTERNAL_DOMAINS = {'google.com', 'bing.com', 'microsoft.com', 'gstatic.com', 'googleusercontent.com'}

IGNORED_MARKDOWN_RESULT_TITLES = {'cached', 'read more', 'translate this result', 'sign in', 'log in', 'images', 'videos', 'shopping', 'news', 'maps', 'web results', 'search results', 'page navigation', 'pagination', 'next', 'previous', 'see more', 'show more', 'view all', 'any time', 'date', 'more results from this site', 'learn more about third party cookies', 'site icon', 'our top picks', 'tell us more'}

IGNORED_MARKDOWN_TITLE_PREFIXES = ('people also ask', 'people also search for', 'related searches', 'videos of ', 'images of ', 'more videos', 'sponsored', 'about our ads')


class SerpMarkdownParser:
    def __init__(self, ports):
        self.ports = ports

    def clean_serp_markdown(self, markdown):
        """
        Remove embedded images and response-printing artifacts before
        parsing.
        """
        markdown = str(markdown or '')
        markdown = re.sub('!\\[[^\\]]*\\]\\(data:image[^)]*\\)', '', markdown, flags=re.IGNORECASE | re.DOTALL)
        markdown = re.sub('<Response\\s*\\[\\d+\\]>', '', markdown, flags=re.IGNORECASE)
        markdown = markdown.replace('\r\n', '\n')
        markdown = re.sub('\\n{4,}', '\n\n', markdown)
        return markdown.strip()

    def clean_displayed_url(self, value):
        """
        Convert a displayed SERP URL into a usable URL.
        """
        value = str(value or '').strip()
        if not value.startswith(('http://', 'https://')):
            return ''
        value = value.split(' › ', 1)[0]
        value = value.split()[0]
        value = value.rstrip('.,;:)]')
        return value

    def result_snippet_from_lines(self, lines):
        ignored_prefixes = ('http://', 'https://', '](', '[read more]', 'read more', 'cached', 'translate this result')
        candidates = []
        for line in lines:
            line = re.sub('\\s+', ' ', str(line or '')).strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered.startswith(ignored_prefixes):
                continue
            if line.startswith(('[', ']', '!', '#')):
                continue
            if lowered in {'view all', 'see more', 'show all', 'images', 'videos'}:
                continue
            if len(line) < 35:
                continue
            candidates.append(line)
        return max(candidates, key=len) if candidates else ''

    def strict_parse_google_markdown(self, markdown, query, num_results=20, requested_country='US'):
        """
        Parse classic organic results from Google Markdown.

        Rich-result modules are skipped. Organic results are assigned
        sequential organic rank after filtering.
        """
        markdown = self.clean_serp_markdown(markdown)
        if '# Search Results' not in markdown:
            raise BrightDataAPIError('Google Markdown did not contain the Search Results marker.')
        search_body = markdown.split('# Search Results', 1)[1]
        if '# Page navigation' in search_body:
            search_body = search_body.split('# Page navigation', 1)[0]
        lines = search_body.splitlines()
        modules = {'people also ask', 'people also search for', 'videos', 'short videos', 'images', 'news', 'forums', 'shopping'}
        blocks = []
        current = None
        in_web_results = False

        def flush_current():
            nonlocal current
            if current:
                blocks.append(current)
                current = None
        for raw_line in lines:
            line = raw_line.strip()
            lowered = line.lower()
            if lowered == '## web results':
                flush_current()
                in_web_results = True
                continue
            if lowered in modules or any((lowered.startswith(module + ' ') for module in modules)):
                flush_current()
                in_web_results = False
                continue
            if line.startswith('## ') and lowered != '## web results':
                flush_current()
                in_web_results = False
                continue
            if in_web_results and line.startswith('### '):
                flush_current()
                current = {'title': line[4:].strip(), 'lines': []}
                continue
            if current is not None:
                current['lines'].append(raw_line)
        flush_current()
        results = []
        seen = set()
        for block in blocks:
            title = re.sub('\\s+', ' ', block['title']).strip()
            block_text = '\n'.join(block['lines'])
            displayed_url = ''
            for line in block['lines']:
                candidate = self.clean_displayed_url(line)
                if not candidate:
                    continue
                hostname = self.ports.get_hostname(candidate)
                if hostname and 'google.' not in hostname:
                    displayed_url = candidate
                    break
            goto_match = re.search('\\]\\((/goto\\?url=[^)]+)\\)', block_text)
            resolved_url = ''
            if goto_match:
                goto_url = 'https://www.google.com' + goto_match.group(1)
                if self.ports.resolve_google_goto_url is not None:
                    resolved_url = self.ports.resolve_google_goto_url(goto_url)
            final_url = resolved_url or displayed_url
            domain = self.ports.get_root_domain(final_url)
            if not domain:
                continue
            dedupe_key = self.ports.canonical_source_url(final_url) or domain + '|' + title.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append({'rank': len(results) + 1, 'raw_serp_position': len(results) + 1, 'title': title, 'url': final_url, 'domain': domain, 'description': self.result_snippet_from_lines(block['lines'])})
            if len(results) >= num_results:
                break
        locale_match = re.search('[?&]hl=([a-z]{2})(?:-([A-Z]{2}))?', markdown)
        observed_language = locale_match.group(1) if locale_match else None
        observed_country = locale_match.group(2) if locale_match and locale_match.group(2) else None
        requested_country = str(requested_country or '').upper()
        localization_warning = bool(observed_country and requested_country and (observed_country != requested_country))
        return {'query': query, 'engine': 'google', 'results': results, 'raw_result_count': len(results), 'requested_country': requested_country, 'observed_language': observed_language, 'observed_country': observed_country, 'localization_warning': localization_warning}

    def decode_bing_redirect(self, url):
        """
        Decode the destination embedded in Bing's u=a1... tracking
        parameter.
        """
        from urllib.parse import parse_qs, unquote, urlparse
        import base64
        url = str(url or '').strip()
        if not url:
            return ''
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            encoded = query.get('u', [''])[0]
            encoded = unquote(encoded)
            if encoded.startswith('a1'):
                encoded = encoded[2:]
            if not encoded:
                return ''
            padding = '=' * ((4 - len(encoded) % 4) % 4)
            decoded = base64.urlsafe_b64decode(encoded + padding).decode('utf-8', errors='ignore').strip()
            if decoded.startswith(('http://', 'https://')):
                return decoded
        except Exception:
            pass
        return ''

    def strict_parse_bing_markdown(self, markdown, query, num_results=20, requested_country='US'):
        """
        Parse classic Bing organic results while excluding ads, Copilot
        summaries, videos, images and related searches.
        """
        markdown = self.clean_serp_markdown(markdown)
        lines = markdown.splitlines()
        heading_pattern = re.compile('^[ \\t]*## \\[(.+?)\\]\\((https?://(?:www\\.)?bing\\.com/(?:ck/a|aclk)\\?[^)]+)\\)')
        headings = [(index, match) for index, line in enumerate(lines) if (match := heading_pattern.match(line))]
        blocks = []
        for position, (index, match) in enumerate(headings):
            next_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
            prior_lines = lines[max(0, index - 8):index]
            near_lines = prior_lines + lines[index:min(index + 4, next_index)]
            rank_markers = [int(rank.group(1)) for line in prior_lines if (rank := re.match('^\\s*(\\d+)\\.\\s+', line))]
            blocks.append({'raw_position': rank_markers[-1] if rank_markers else position + 1, 'lines': lines[index:min(index + 8, next_index)], 'near_lines': near_lines, 'title_match': match})
        rejected_markers = ('sponsored', 'gesponsert', 'anzeigen', 'adsplus', 'about our ads', 'this summary was generated by ai', 'content was generated with ai', 'videos of ', 'images of ', 'people also search for', 'deep dive into', 'pagination', 'some results have been removed')
        results = []
        seen = set()
        for block in blocks:
            block_text = '\n'.join(block['near_lines'])
            block_lower = block_text.lower()
            if any((marker in block_lower for marker in rejected_markers)):
                continue
            title_match = block['title_match']
            if not title_match:
                continue
            title = re.sub('\\s+', ' ', title_match.group(1)).strip()
            if title.lower().startswith(('videos of ', 'images of ', 'more videos')):
                continue
            if title.casefold() in {'any time', 'date', 'more results from this site', 'learn more about third party cookies'}:
                continue
            tracking_url = title_match.group(2)
            if '/aclk?' in tracking_url:
                continue
            decoded_url = self.decode_bing_redirect(tracking_url)
            displayed_url = ''
            for line in block['lines']:
                candidate = self.clean_displayed_url(line)
                if not candidate:
                    continue
                hostname = self.ports.get_hostname(candidate)
                if hostname and (not hostname.endswith('bing.com')) and (not hostname.endswith('microsoft.com')):
                    displayed_url = candidate
                    break
            final_url = decoded_url or displayed_url
            domain = self.ports.get_root_domain(final_url)
            if not domain:
                continue
            if domain in {'bing.com', 'microsoft.com'}:
                continue
            dedupe_key = self.ports.canonical_source_url(final_url) or domain + '|' + title.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append({'rank': len(results) + 1, 'raw_serp_position': block['raw_position'], 'title': title, 'url': final_url, 'domain': domain, 'description': self.result_snippet_from_lines(block['lines'])})
            if len(results) >= num_results:
                break
        return {'query': query, 'engine': 'bing', 'results': results, 'raw_result_count': len(results), 'requested_country': str(requested_country or '').upper(), 'observed_language': None, 'observed_country': None, 'localization_warning': False}

    def clean_markdown_result_title(self, title):
        title = str(title or '')
        title = re.sub('!\\[[^\\]]*\\]', '', title)
        title = re.sub('[*_`#]+', '', title)
        title = re.sub('\\s+', ' ', title).strip()
        return title

    def markdown_title_is_usable(self, title):
        normalized = self.clean_markdown_result_title(title).lower()
        if not normalized:
            return False
        if normalized in IGNORED_MARKDOWN_RESULT_TITLES:
            return False
        if any((normalized.startswith(prefix) for prefix in IGNORED_MARKDOWN_TITLE_PREFIXES)):
            return False
        if len(normalized) < 3:
            return False
        return True

    def normalize_markdown_destination(self, value):
        value = str(value or '').strip()
        value = value.replace('&amp;', '&').replace('\\&', '&')
        if value.startswith('<') and value.endswith('>'):
            value = value[1:-1].strip()
        return value

    def external_url_is_usable(self, value):
        value = str(value or '').strip()
        if not value.startswith(('http://', 'https://')):
            return False
        root_domain = self.ports.get_root_domain(value)
        if not root_domain:
            return False
        if root_domain in SERP_INTERNAL_DOMAINS:
            return False
        return True

    def find_nearby_external_url(self, block_lines):
        """
        Prefer the displayed destination URL located near a result title.
        This avoids unnecessary redirect requests and handles expired
        Google /goto tokens.
        """
        block_text = '\n'.join(block_lines)
        for match in DIRECT_HTTP_URL_PATTERN.finditer(block_text):
            candidate = match.group(0).rstrip('.,;:!?)]}')
            if self.external_url_is_usable(candidate):
                return candidate
        return ''

    def resolve_google_markdown_url(self, raw_url, block_lines):
        raw_url = self.normalize_markdown_destination(raw_url)
        nearby_url = self.find_nearby_external_url(block_lines)
        if nearby_url:
            return nearby_url
        if raw_url.startswith('//'):
            raw_url = 'https:' + raw_url
        if raw_url.startswith('/goto?'):
            full_url = urljoin('https://www.google.com/', raw_url)
            resolved = self.ports.resolve_google_goto_url(full_url)
            if self.external_url_is_usable(resolved):
                return resolved
            return ''
        parsed = urlparse(raw_url)
        if raw_url.startswith('/url?') or (
            self.ports.get_root_domain(raw_url) == 'google.com'
            and parsed.path == '/url'
        ):
            query = parse_qs(parsed.query)
            destination = query.get('q', [''])[0] or query.get('url', [''])[0]
            destination = unquote(destination).strip()
            if self.external_url_is_usable(destination):
                return destination
            return ''
        if raw_url.startswith('/'):
            return ''
        if self.ports.is_google_goto_url(raw_url):
            resolved = self.ports.resolve_google_goto_url(raw_url)
            if self.external_url_is_usable(resolved):
                return resolved
            return ''
        if self.external_url_is_usable(raw_url):
            return raw_url
        return ''

    def resolve_bing_markdown_url(self, raw_url, block_lines):
        raw_url = self.normalize_markdown_destination(raw_url)
        if raw_url.startswith('//'):
            raw_url = 'https:' + raw_url
        if raw_url.startswith('/'):
            raw_url = urljoin('https://www.bing.com/', raw_url)
        raw_domain = self.ports.get_root_domain(raw_url)
        if raw_domain in {'bing.com', 'microsoft.com'}:
            decoded = self.decode_bing_redirect(raw_url)
            if self.external_url_is_usable(decoded):
                return decoded
            nearby_url = self.find_nearby_external_url(block_lines)
            if nearby_url:
                return nearby_url
            return ''
        if self.external_url_is_usable(raw_url):
            return raw_url
        return self.find_nearby_external_url(block_lines)

    def resolve_markdown_result_url(self, raw_url, engine, block_lines):
        engine = str(engine or '').strip().lower()
        if engine == 'google':
            return self.resolve_google_markdown_url(raw_url, block_lines)
        if engine == 'bing':
            return self.resolve_bing_markdown_url(raw_url, block_lines)
        return ''

    def markdown_result_blocks(self, markdown):
        """
        Find Markdown links and associate each link with nearby text.

        The fallback does not depend on a specific heading level, numbered
        block format, or "Web results" marker.
        """
        lines = str(markdown or '').splitlines()
        candidates = []
        for line_index, line in enumerate(lines):
            for match in MARKDOWN_RESULT_LINK_PATTERN.finditer(line):
                title = self.clean_markdown_result_title(match.group('title'))
                if not self.markdown_title_is_usable(title):
                    continue
                candidates.append({'line_index': line_index, 'title': title, 'raw_url': match.group('url')})
        blocks = []
        for index, candidate in enumerate(candidates):
            start = candidate['line_index']
            if index + 1 < len(candidates):
                next_start = candidates[index + 1]['line_index']
                end = min(next_start, start + 14)
            else:
                end = min(len(lines), start + 14)
            block_lines = lines[start:end]
            blocks.append({**candidate, 'lines': block_lines})
        return blocks

    def parse_generic_markdown_serp(self, markdown, query, engine, num_results=20, requested_country='US'):
        markdown = self.clean_serp_markdown(markdown)
        blocks = self.markdown_result_blocks(markdown)
        results = []
        seen = set()
        rejected = []
        for block in blocks:
            final_url = self.resolve_markdown_result_url(raw_url=block['raw_url'], engine=engine, block_lines=block['lines'])
            domain = self.ports.get_root_domain(final_url)
            if not domain:
                rejected.append({'title': block['title'], 'raw_url': block['raw_url'], 'reason': 'No external destination URL could be resolved.'})
                continue
            if domain in {'google.com', 'bing.com', 'microsoft.com'}:
                continue
            canonical = self.ports.canonical_source_url(final_url) or domain + '|' + block['title'].lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            description = self.result_snippet_from_lines(block['lines'])
            results.append({'rank': len(results) + 1, 'raw_serp_position': block['line_index'], 'title': block['title'], 'url': final_url, 'domain': domain, 'description': description})
            if len(results) >= num_results:
                break
        diagnostics = {'engine': engine, 'query': query, 'parser': 'generic_markdown', 'link_candidates': len(blocks), 'usable_results': len(results), 'rejected_count': len(rejected), 'rejected_preview': rejected[:10], 'heading_preview': [line.strip()[:300] for line in markdown.splitlines() if line.strip().startswith('#')][:30], 'markdown_preview': markdown[:3000]}
        self.ports.diagnostics[engine] = diagnostics
        return {'query': query, 'engine': engine, 'results': results, 'raw_result_count': len(blocks), 'requested_country': str(requested_country or '').upper(), 'observed_language': None, 'observed_country': None, 'localization_warning': False, 'parser': 'generic_markdown', 'parser_diagnostics': diagnostics}

    def parse_google_markdown(self, markdown, query, num_results=20, requested_country='US'):
        strict_error = None
        try:
            strict_result = self.strict_parse_google_markdown(markdown=markdown, query=query, num_results=num_results, requested_country=requested_country)
            if isinstance(strict_result, dict) and strict_result.get('results'):
                strict_result['parser'] = 'strict_google'
                return strict_result
        except Exception as exc:
            strict_error = f'{type(exc).__name__}: {exc}'
        fallback_result = self.parse_generic_markdown_serp(markdown=markdown, query=query, engine='google', num_results=num_results, requested_country=requested_country)
        fallback_result['strict_parser_error'] = strict_error
        return fallback_result

    def parse_bing_markdown(self, markdown, query, num_results=20, requested_country='US'):
        strict_error = None
        try:
            strict_result = self.strict_parse_bing_markdown(markdown=markdown, query=query, num_results=num_results, requested_country=requested_country)
            if isinstance(strict_result, dict):
                strict_result['parser'] = 'strict_bing'
                return strict_result
        except Exception as exc:
            strict_error = f'{type(exc).__name__}: {exc}'
        return {'query': query, 'engine': 'bing', 'results': [], 'raw_result_count': 0, 'requested_country': requested_country, 'parser': 'strict_bing', 'strict_parser_error': strict_error}
