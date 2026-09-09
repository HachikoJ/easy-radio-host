// match `[12:30.1][12:30.2]`
export const SQUARE_TAGS_REGEXP = /^(?:\s*\[[^\]]+\])+/;
// match `ti: The Title`
export const INFO_REGEXP = /^\s*(\w+)\s*:(.*)$/;
// match `512:34.1`
export const TIME_REGEXP = /^\s*(\d+)\s*:\s*(\d+(\s*[.:]\s*\d+)?)\s*$/;
// match `<12:30.1> word` (A2 extension) | `[12:30.1] word` (Foobar2000)
export const ENHANCED_TAG_WORD_REGEXP = /[<[](\d+:\d+(?:\.\d+)?)[>\]]([^[<]*)/;
export var LineType;
(function (LineType) {
    LineType["INVALID"] = "INVALID";
    LineType["INFO"] = "INFO";
    LineType["TIME"] = "TIME";
})(LineType || (LineType = {}));
export function parseSquareTags(line) {
    line = line.trim();
    const matches = SQUARE_TAGS_REGEXP.exec(line);
    if (matches === null)
        return null;
    const tag = matches[0];
    const content = line.slice(tag.length);
    return {
        tags: tag.slice(1, -1).split(/\]\s*\[/),
        rawContent: content,
    };
}
function parseTimestamp(str) {
    var _a, _b;
    const matches = TIME_REGEXP.exec(str);
    if (!matches)
        return null;
    const minuteStr = (_a = matches[1]) !== null && _a !== void 0 ? _a : '0';
    const secondStr = (_b = matches[2]) !== null && _b !== void 0 ? _b : '0';
    const minutes = parseFloat(minuteStr);
    const seconds = parseFloat(secondStr.replace(/\s+/g, '').replace(':', '.'));
    return minutes * 60 + seconds;
}
export function parseEnhancedWords(timestamps, rawContent) {
    const wordTimestamps = [];
    let stripContent = '';
    let stripIndex = 0;
    const pushContent = (timestamp, wordContent) => {
        if (!wordContent.trim())
            return;
        if (stripContent.endsWith(' ') && wordContent.startsWith(' ')) {
            wordContent = wordContent.trimStart();
        }
        stripContent += wordContent;
        wordTimestamps.push({
            timestamp,
            content: wordContent,
        });
    };
    const firstTimestamp = timestamps[timestamps.length - 1];
    if (!firstTimestamp)
        return null;
    const firstMatches = ENHANCED_TAG_WORD_REGEXP.exec(rawContent);
    const firstContent = firstMatches
        ? rawContent.slice(0, firstMatches.index)
        : rawContent;
    pushContent(firstTimestamp, firstContent);
    if (firstMatches)
        while (stripIndex < rawContent.length) {
            const wordMatches = ENHANCED_TAG_WORD_REGEXP.exec(rawContent.slice(stripIndex));
            if (!wordMatches)
                break;
            stripIndex += wordMatches.index + wordMatches[0].length;
            const timestamp = parseTimestamp(wordMatches[1]);
            if (timestamp === null)
                continue;
            const wordContent = wordMatches[2];
            pushContent(timestamp, wordContent);
        }
    return {
        type: LineType.TIME,
        timestamps,
        content: stripContent.trim(),
        rawContent,
        wordTimestamps,
    };
}
export function parseTime(tags, rawContent, { enhanced = true } = {}) {
    const timestamps = tags
        .map((tag) => parseTimestamp(tag))
        .filter((it) => it !== null);
    rawContent = rawContent.trim();
    if (enhanced) {
        const parsedWords = parseEnhancedWords(timestamps, rawContent);
        if (parsedWords)
            return parsedWords;
    }
    return {
        type: LineType.TIME,
        timestamps,
        rawContent,
        content: rawContent,
    };
}
export function parseInfo(tag) {
    var _a, _b;
    const matches = INFO_REGEXP.exec(tag);
    if (!matches)
        return null;
    const key = (_a = matches[1]) !== null && _a !== void 0 ? _a : '';
    const value = (_b = matches[2]) !== null && _b !== void 0 ? _b : '';
    return {
        type: LineType.INFO,
        key: key.trim(),
        value: value.trim(),
    };
}
const parseLineInner = (line, options) => {
    const parsedTags = parseSquareTags(line);
    if (!parsedTags)
        return null;
    const { tags, rawContent } = parsedTags;
    const firstTag = tags[0];
    if (!firstTag)
        return null;
    if (TIME_REGEXP.test(firstTag)) {
        return parseTime(tags, rawContent, options);
    }
    else {
        return parseInfo(firstTag);
    }
};
/**
 * line parse lrc of timestamp
 * @example
 * const lp = parseLine('[ti: Song title]')
 * lp.type === LineParser.TYPE.INFO
 * lp.key === 'ti'
 * lp.value === 'Song title'
 *
 * const lp = parseLine('[10:10.10]hello')
 * lp.type === LineParser.TYPE.TIME
 * lp.timestamps === [10*60+10.10]
 * lp.content === 'hello'
 *
 * const lp = parseLine('[10:10.10] <10:10.12> hello <10:11.02> world')
 * lp.type === LineParser.TYPE.TIME
 * lp.timestamps === [10*60+10.10]
 * lp.content === 'hello world'
 * lp.wordTimestamps === [
 *  { timestamp: 10*60+10.12, content: 'hello' },
 *  { timestamp: 10*60+11.02, content: 'world' }
 * ]
 */
export function parseLine(line, options) {
    const result = parseLineInner(line, options);
    return result
        ? result
        : {
            type: LineType.INVALID,
        };
}
