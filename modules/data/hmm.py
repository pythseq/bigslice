#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
#
# Copyright (C) 2019 Satria A. Kautsar
# Wageningen University & Research
# Bioinformatics Group
"""bigsscuit.modules.data.hmm

Handle registration of hmm tables and
performing hmmscan of aa sequences
"""

from os import path
from .database import Database
import glob


class HMMDatabase:
    """Represents an hmm_db entry in the database"""
    # TODO: saving an HMM at a time is VERY SLOW!!
    # make a batch saving procedure instead

    def __init__(self, properties: dict, database: Database):
        self.database = database
        self.id = properties.get("id", -1)
        self.md5_biosyn_pfam = properties["md5_biosyn_pfam"]
        self.md5_sub_pfam = properties["md5_sub_pfam"]
        self.biosyn_pfams = properties["biosyn_pfams"]
        self.sub_pfams = properties["sub_pfams"]

    def save(self):
        """commits hmm_db data"""

        existing = self.database.select(
            "hmm_db",
            "WHERE md5_biosyn_pfam=? AND md5_sub_pfam=?",
            parameters=(self.md5_biosyn_pfam, self.md5_sub_pfam)
        ).fetchall()
        if existing:
            # current behavior: check if there is conflict
            # don't do anything if the same hmm_db exists
            assert len(existing) == 1
            existing = existing[0]
            if False:  # TODO: implements checking
                raise Exception("conflicting HMM_DB entry exists.")
            else:
                self.id = existing["id"]
                for biosyn_pfam in self.biosyn_pfams:
                    biosyn_pfam.id = int(self.database.select(
                        "hmm",
                        "WHERE name=? AND db_id=?",
                        parameters=(biosyn_pfam.name, self.id),
                        props=["id"]
                    ).fetchall()[0]["id"])
                for parent_acc in self.sub_pfams:
                    parent_id = int(self.database.select(
                        "hmm",
                        "WHERE accession=? AND db_id=?",
                        parameters=(parent_acc, self.id),
                        props=["id"]
                    ).fetchall()[0]["id"])
                    for sub_pfam in self.sub_pfams[parent_acc]:
                        sub_pfam.parent_id = parent_id
                        sub_pfam.id = int(self.database.select(
                            "hmm,subpfam",
                            "WHERE hmm.id=subpfam.hmm_id AND " +
                            "parent_hmm_id=? AND " +
                            "hmm.name=? AND hmm.db_id=?",
                            parameters=(parent_id, sub_pfam.name, self.id)
                        ).fetchall()[0]["id"])

        else:
            # insert new hmm_db
            self.id = self.database.insert(
                "hmm_db",
                {
                    "md5_biosyn_pfam": self.md5_biosyn_pfam,
                    "md5_sub_pfam": self.md5_sub_pfam
                }
            )
            # insert biosyn_pfam hmms
            for biosyn_pfam in self.biosyn_pfams:
                biosyn_pfam.db_id = self.id
                biosyn_pfam.__save__(self.database)
            # insert sub_pfam hmms
            for parent_acc in self.sub_pfams:
                parent_id = int(self.database.select(
                    "hmm",
                    "WHERE accession=? AND db_id=?",
                    parameters=(parent_acc, self.id),
                    props=["id"]
                ).fetchall()[0]["id"])
                for sub_pfam in self.sub_pfams[parent_acc]:
                    sub_pfam.db_id = self.id
                    sub_pfam.parent_id = parent_id
                    sub_pfam.__save__(self.database)

    @staticmethod
    def load_folder(db_folder_path: str, database: Database,
                    immediately_commits: bool=False):
        """Loads a folder containing hmm models generated by
        generate_databases.py"""

        # get md5sums values and paths to hmm models
        biosyn_pfam_hmm = path.join(
            db_folder_path, "biosynthetic_pfams", "Pfam-A.biosynthetic.hmm")
        md5_biosyn_pfam = open(path.join(
            db_folder_path, "biosynthetic_pfams",
            "biopfam.md5sum"), "r").readline().rstrip()
        sub_pfam_hmms = glob.glob(path.join(
            db_folder_path, "sub_pfams", "hmm", "*.subpfams.hmm"))
        md5_sub_pfam = open(path.join(
            db_folder_path, "sub_pfams",
            "corepfam.md5sum"), "r").readline().rstrip()

        # fetch hmm objects
        biosyn_pfams = HMMDatabase.HMM.from_file(biosyn_pfam_hmm)
        sub_pfams = {}
        for sub_pfam_hmm in sub_pfam_hmms:
            parent_acc = path.basename(
                sub_pfam_hmm).split(".subpfams.hmm")[0]
            sub_pfams[parent_acc] = HMMDatabase.HMM.from_file(sub_pfam_hmm)

        result = HMMDatabase({
            "md5_biosyn_pfam": md5_biosyn_pfam,
            "md5_sub_pfam": md5_sub_pfam,
            "biosyn_pfams": biosyn_pfams,
            "sub_pfams": sub_pfams
        }, database)

        if immediately_commits:
            result.save()

        return result

    class HMM:
        """Represents one hmm model
        Currently, hmm models are part of a hmm_db,
        meaning that a pfam accession will be considered
        different when linked to two separate hmm_dbs"""

        def __init__(self, properties: dict):
            self.id = properties.get("id", -1)
            self.parent_id = properties.get("parent_id", -1)
            self.db_id = properties.get("db_id", -1)
            self.accession = properties.get("accession", None)
            self.name = properties["name"]
            self.model_length = properties["model_length"]

        def __save__(self, database: Database):
            """commit hmm
            this only meant to be called from HMMDatabase.save()"""
            assert self.db_id > -1
            existing = database.select(
                "hmm",
                "WHERE name=? AND db_id=?",
                parameters=(self.name, self.db_id)
            ).fetchall()
            if existing:
                # current behavior: check if there is conflict
                # don't do anything if the same entry exists
                assert len(existing) == 1
                existing = existing[0]
                if self.model_length != existing["model_length"]:
                    raise Exception("conflicting HMM entry for " +
                                    self.name)
                else:
                    self.id = existing["id"]
            else:
                # insert new hmm
                self.id = database.insert(
                    "hmm",
                    {
                        "db_id": self.db_id,
                        "name": self.name,
                        "accession": self.accession,
                        "model_length": self.model_length
                    }
                )
                if self.parent_id > -1:
                    # insert subpfam relationship
                    database.insert(
                        "subpfam",
                        {
                            "hmm_id": self.id,
                            "parent_hmm_id": self.parent_id
                        }
                    )

        @staticmethod
        def from_file(hmm_path: str):
            """Parse an hmm file, return all HMM objects"""

            results = []
            with open(hmm_path, "r") as hmm_file:
                properties = {}
                for line in hmm_file.readlines():
                    line = line.rstrip()
                    if line.startswith("NAME"):
                        properties["name"] = line.split(" ")[-1]
                    elif line.startswith("ACC"):
                        properties["accession"] = line.split(" ")[-1]
                    elif line.startswith("LENG"):
                        properties["model_length"] = int(
                            line.split(" ")[-1].rstrip())
                    elif line == "//":
                        results.append(HMMDatabase.HMM(properties))
                        properties = {}
                if properties != {}:
                    results.append(HMMDatabase.HMM(properties))
            return results
