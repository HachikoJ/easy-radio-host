import { parseLine, LineType } from './line-parser.js';
function padStartZero2(num) {
    return num.toString().padStart(2, '0');
}
/**
 * get lrc time string
 * @example
 * Lrc.timestampToString(143.54)
 * // return '02:23.54':
 * @param timestamp second timestamp
 */
export function timestampToString(timestamp) {
    const minutes = Math.floor(timestamp / 60);
    const secondsFraction = timestamp % 60;
    const seconds = Math.floor(secondsFraction);
    const fraction = Math.round((secondsFraction - seconds) * 100);
    return `${padStartZero2(minutes)}:${padStartZero2(seconds)}.${fraction.toString().padEnd(2, '0')}`;
}
export class Lrc {
    constructor() {
        this.info = {};
        this.lyrics = [];
        this.plain = '';
    }
    /**
     * parse lrc text and return a Lrc object
     */
    static parse(text, options) {
        const lyrics = [];
        const info = {};
        let plain = '';
        const lines = text.split(/\r\n|[\n\r]/g).map((line) => {
            return parseLine(line, options);
        });
        for (const line of lines) {
            switch (line.type) {
                case LineType.INFO:
                    info[line.key] = line.value;
                    break;
                case LineType.TIME:
                    for (const timestamp of line.timestamps) {
                        lyrics.push({
                            timestamp,
                            wordTimestamps: line.wordTimestamps,
                            rawContent: line.rawContent,
                            content: line.content,
                        });
                        plain += `${line.content}\n`;
                    }
                    break;
                default:
                    break;
            }
        }
        const lrc = new this();
        lrc.lyrics = lyrics;
        lrc.info = info;
        lrc.plain = plain;
        return lrc;
    }
    offset(offsetTime) {
        for (const lyric of this.lyrics) {
            lyric.timestamp += offsetTime;
            if (lyric.timestamp < 0) {
                lyric.timestamp = 0;
            }
        }
    }
    clone() {
        function clonePlainObject(obj) {
            return JSON.parse(JSON.stringify(obj));
        }
        const lrc = new Lrc();
        lrc.info = clonePlainObject(this.info);
        lrc.lyrics = clonePlainObject(this.lyrics);
        return lrc;
    }
    /**
     * get lrc text
     * @param opts.combine lyrics combine by same content
     * @param opts.sort lyrics sort by timestamp
     * @param opts.lineFormat newline format
     */
    toString({ combine = true, lineFormat = '\r\n', sort = true, } = {}) {
        const lines = [];
        // generate info
        for (const [key, value] of Object.entries(this.info)) {
            lines.push(`[${key}:${value}]`);
        }
        if (combine) {
            const lyricsMap = new Map();
            const lyricsList = [];
            // uniqueness
            for (const lyric of this.lyrics) {
                const existLyric = lyricsMap.get(lyric.rawContent);
                if (existLyric) {
                    existLyric[0].push(lyric.timestamp);
                }
                else {
                    lyricsMap.set(lyric.rawContent, [
                        [lyric.timestamp],
                        lyric.rawContent,
                    ]);
                }
            }
            // sorted
            for (const [content, value] of lyricsMap.entries()) {
                lyricsList.push({
                    timestamps: value[0],
                    rawContent: value[1],
                    content,
                });
            }
            if (sort) {
                lyricsList.sort((a, b) => { var _a, _b; return ((_a = a.timestamps[0]) !== null && _a !== void 0 ? _a : 0) - ((_b = b.timestamps[0]) !== null && _b !== void 0 ? _b : 0); });
            }
            // generate lyrics
            for (const lyric of lyricsList) {
                lines.push(`[${lyric.timestamps
                    .map((timestamp) => timestampToString(timestamp))
                    .join('][')}]${lyric.rawContent || ''}`);
            }
        }
        else {
            for (const lyric of this.lyrics) {
                lines.push(`[${timestampToString(lyric.timestamp)}]${lyric.content || ''}`);
            }
        }
        return lines.join(lineFormat);
    }
}
