import { describe, expect, it } from "vitest";
import { errorsFromServer, toForm, toPayload } from "./settingsForm";

const values = {
  music_folder: "/music/mp3",
  bandcamp_folder: null,
  rekordbox_db: "/rb/master.db",
  tag_mapping: null,
  target_format: "mp3",
  ffmpeg_quality: 2,
  download_quality: "LOSSLESS",
  prune_tracks: true,
  backups_keep_full: 20,
  backups_keep_db: 10,
  port: 8765,
};

describe("toForm / toPayload", () => {
  it("round-trips values; empty optional paths become null", () => {
    const form = toForm(values);
    expect(form.bandcamp_folder).toBe("");
    const { values: payload, errors } = toPayload(form);
    expect(errors).toEqual({});
    expect(payload).toEqual(values);
  });

  it("trims text and reports bad numbers and a missing Music folder", () => {
    const form = {
      ...toForm(values),
      music_folder: "  ",
      bandcamp_folder: " /bc ",
      port: "80a",
      ffmpeg_quality: "",
    };
    const { values: payload, errors } = toPayload(form);
    expect(payload.bandcamp_folder).toBe("/bc");
    expect(errors).toEqual({
      music_folder: "Required",
      port: "Enter a whole number",
      ffmpeg_quality: "Required",
    });
  });
});

describe("errorsFromServer", () => {
  it("puts field errors next to fields and unknown ones into _form", () => {
    const errors = errorsFromServer(
      [
        {
          field: "ffmpeg_quality",
          loc: ["ffmpeg_quality"],
          message: "Input should be less than or equal to 9",
        },
        { field: "colour", loc: ["colour"], message: "Extra inputs are not permitted" },
      ],
      "Invalid settings",
    );
    expect(errors.ffmpeg_quality).toBe("Input should be less than or equal to 9");
    expect(errors._form).toBe("colour: Extra inputs are not permitted");
  });

  it("falls back to the message when there are no field errors", () => {
    expect(errorsFromServer([], "Server error")).toEqual({ _form: "Server error" });
  });
});
