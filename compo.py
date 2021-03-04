#!/usr/bin/env python3

import datetime
import uuid
import logging
import statistics
from typing import Optional
import pickle


current_week = None
next_week = None


def get_week(get_next_week: bool) -> dict:
    """
    Returns a dictionary that encodes information for a week's challenge. If
    the requested week has no information, attempts to read previously
    serialized information. If the pickle object was not found, returns
    a new dictionary.

    Parameters
    ----------
    get_next_week : bool
        Whether the week that should be retrieved is the following week.
        False returns the current week's information, while True retrieves
        next week's information.

    Returns
    -------
    dict
        A dictionary that encodes information for a week. The information
        includes theme, date, whether submissions are open, and a list of
        entries.
    """
    global current_week, next_week

    if current_week is None:
        try:
            current_week = pickle.load(open("weeks/current-week.pickle", "rb"))
        except FileNotFoundError:
            current_week = {
                "theme": "Week XYZ: Fill this in by hand!",
                "date": "Month day'th 20XX",
                "submissionsOpen": False,
                "votingOpen": True,
                "entries": []
            }
    if next_week is None:
        try:
            next_week = pickle.load(open("weeks/next-week.pickle", "rb"))
        except FileNotFoundError:
            next_week = {
                "theme": "Week XYZ: Fill this in by hand!",
                "date": "Month day'th 20XX",
                "submissionsOpen": True,
                "votingOpen": True,
                "entries": []
            }

    if get_next_week:
        return next_week
    else:
        return current_week


def save_weeks() -> None:
    """
    Saves `current_week` and `next_week` into pickle objects so that they can
    later be read again.
    """
    if current_week is not None and next_week is not None:
        pickle.dump(current_week, open("weeks/current-week.pickle", "wb"))
        pickle.dump(next_week, open("weeks/next-week.pickle", "wb"))
        logging.info("COMPO: current-week.pickle and next-week.pickle overwritten")


def move_to_next_week() -> None:
    """
    Replaces `current_week` with `next_week`, freeing up `next_week` to be
    replaced with new information.

    Calls `save_weeks()` to serialize the data after modification.
    """
    global current_week, next_week

    archive_filename = "weeks/archive/" + \
        datetime.datetime.now().strftime("%m-%d-%y") + ".pickle"
    pickle.dump(current_week, open(archive_filename, "wb"))

    current_week = next_week
    next_week = {
        "theme": "Week XYZ: Fill this in by hand!",
        "date": "Month day'th 20XX",
        "submissionsOpen": True,
        "votingOpen": True,
        "entries": []
    }

    save_weeks()


def create_blank_entry(entrant_name: str,
                       discord_id: Optional[int],
                       get_next_week: bool = True) -> str:
    """
    Create a blank entry for an entrant and returns a UUID

    Parameters
    ----------
    entrant_name : str
        The name of the entrant
    discord_id : Optional[int]
        The entrant's Discord ID
    get_next_week : bool, optional
        Whether the entry should be for the folowing week, by default True

    Returns
    -------
    str
        A randomly generated UUID
    """
    entry = {
        "entryName": "",
        "entrantName": entrant_name,
        "discordID": discord_id,
        "uuid": str(uuid.uuid4())
    }
    get_week(get_next_week)["entries"].append(entry)

    return entry["uuid"]


def find_entry_by_uuid(uuid: str) -> Optional[dict]:
    for which_week in [True, False]:
        for entry in get_week(which_week)["entries"]:
            if entry["uuid"] == uuid:
                return entry
    return None


def entry_valid(entry: dict) -> bool:
    requirements = [
        "uuid",
        "pdf",
        "pdfFilename",
        "mp3",
        "mp3Format",
        "mp3Filename",
        "entryName",
        "entrantName",
    ]

    for requirement in requirements:
        if requirement not in entry:
            return False

    for param in ["mp3", "pdf"]:
        if entry[param] is None:
            return False

    return True


def count_valid_entries(which_week: bool) -> int:
    count = 0

    for e in get_week(which_week)["entries"]:
        if entry_valid(e):
            count += 1

    return count


def get_entry_file(uuid: str, filename: str) -> tuple:
    entry = find_entry_by_uuid(uuid)
    if entry is None:
        return None, None

    if "mp3Filename" in entry and entry["mp3Filename"] == filename:
        return entry["mp3"], "audio/mpeg"

    if "pdfFilename" in entry and entry["pdfFilename"] == filename:
        return entry["pdf"], "application/pdf"

    return None, None


def verify_votes(week: dict) -> None:
    
    if not "votes" in week:
        week["votes"] = []

    # Keeps track of set vs. unset votes, and makes sure a single user can
    # only vote on the same parameter for the same entry a single time
    userVotes = {}
    
    # Validate data, and throw away sus ratings
    for v in week["votes"]:
        for r in v["ratings"]:
            if not (v["userID"], r["entryUUID"], r["voteParam"]) in userVotes \
                    and r["rating"] <= 5 \
                    and r["rating"] >= 0:
                if r["rating"] == 0: # Unset rating
                    userVotes[(v["userID"], r["entryUUID"], r["voteParam"])] \
                        = False
                else:
                    userVotes[(v["userID"], r["entryUUID"], r["voteParam"])] \
                        = True
                # TODO: throw out ratings for made-up categories
                # (this will involve data-ifying the voteParams into the week)
            else:
                logging.warning("COMPO: FRAUD DETECTED (CHECK VOTES)")
                logging.warning("Sus rating: " + str(r))
                v["ratings"].remove(r)

def get_ranked_entrant_list(which_week: bool) -> list:
    """Bloc STAR Voting wooooo"""

    week = get_week(which_week)

    verify_votes(which_week)

    scores = {}

    # Get rating extents, for normalization
    for v in week["votes"]:
        v["minimum"] = 5
        v["maximum"] = 1
        for r in v["ratings"]:
            if r["rating"] == 0: # Unset rating
                continue
            if r["rating"] > v["maximum"]:
                v["maximum"] = r["rating"]
            if r["rating"] < v["minimum"]:
                v["minimum"] = r["rating"]

    # Evaluate scores
    for v in week["votes"]:
        for r in v["ratings"]:
            if not r["entryUUID"] in scores:
                scores[r["entryUUID"]] = []
            if r["rating"] != 0:
                normalized = float(r["rating"] - (v["minimum"] - 1))
                normalized /= float(v["maximum"] - (v["minimum"] -1))
                normalized *= 5
                scores[r["entryUUID"]].append(normalized)

    entry_pool = []
    ranked_entries = []

    # Write final scores to entry data, and put 'em all in entry_pool
    for e in week["entries"]:
        if entry_valid(e):
            if e["uuid"] in scores:
                e["voteScore"] = statistics.mean(scores[e["uuid"]])
            else:
                e["voteScore"] = 0
            entry_pool.append(e)

    # Now that we have scores calculated, run the actual STAR algorithm
    while len(entry_pool) > 1:
        entry_pool = sorted(entry_pool, key=lambda e: e["voteScore"])

        entryA = entry_pool[0]
        entryB = entry_pool[1]

        preferEntryA = 0
        preferEntryB = 0

        for v in week["votes"]:
            scoreA = 0
            scoreB = 0

            # note that normalization doesn't matter for comparing preference
            for r in v["ratings"]:
                if r["entryUUID"] == entryA["uuid"]:
                    scoreA += r["rating"]
                elif r["entryUUID"] == entryB["uuid"]:
                    scoreB += r["rating"]

            if scoreA > scoreB:
                preferEntryA += 1
            elif scoreB > scoreA:
                preferEntryB += 1

        # greater than or equal to, as entryA is the entry with a higher score,
        # to settle things in the case of a tie
        if preferEntryA >= preferEntryB:
            ranked_entries.append(entry_pool.pop(0))
        else:
            ranked_entries.append(entry_pool.pop(1))

    # Add the one remaining entry
    ranked_entries.insert(0, entry_pool.pop(0))

    for place, e in enumerate(reversed(ranked_entries)):
        e["votePlacement"] = place + 1

    return list(reversed(ranked_entries))
