#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012-2021 Snowflake Computing Inc. All right reserved.
#

import os

import pytest
from mock import patch

try:  # pragma: no cover
    from snowflake.connector.file_transfer_agent_sdk import SnowflakeFileTransferAgent
except ImportError:  # keep olddrivertest from breaking
    from snowflake.connector.file_transfer_agent import SnowflakeFileTransferAgent

from ..generate_test_files import generate_k_lines_of_n_files


@pytest.mark.skipolddriver
@pytest.mark.aws
def test_put_copy_large_files(tmpdir, conn_cnx, db_parameters, sdkless):
    """[s3] Puts and Copies into large files."""
    # generates N files
    number_of_files = 2
    number_of_lines = 200000
    tmp_dir = generate_k_lines_of_n_files(
        number_of_lines, number_of_files, tmp_dir=str(tmpdir.mkdir("data"))
    )

    files = os.path.join(tmp_dir, "file*")
    with conn_cnx(use_new_put_get=sdkless) as cnx:
        cnx.cursor().execute(
            f"""
create table {db_parameters['name']} (
aa int,
dt date,
ts timestamp,
tsltz timestamp_ltz,
tsntz timestamp_ntz,
tstz timestamp_tz,
pct float,
ratio number(6,2))
"""
        )
    try:
        with conn_cnx(use_new_put_get=sdkless) as cnx:
            files = files.replace("\\", "\\\\")

            def mocked_file_agent(*args, **kwargs):
                newkwargs = kwargs.copy()
                newkwargs.update(multipart_threshold=10000)
                agent = SnowflakeFileTransferAgent(*args, **newkwargs)
                mocked_file_agent.agent = agent
                return agent

            with patch(
                "snowflake.connector.cursor.SnowflakeFileTransferAgent"
                if sdkless
                else "snowflake.connector.cursor.SnowflakeFileTransferAgentSdk",
                side_effect=mocked_file_agent,
            ):
                cnx.cursor().execute(
                    f"put 'file://{files}' @%{db_parameters['name']}",
                )
                assert mocked_file_agent.agent._multipart_threshold == 10000

            c = cnx.cursor()
            try:
                c.execute("copy into {}".format(db_parameters["name"]))
                cnt = 0
                for _ in c:
                    cnt += 1
                assert cnt == number_of_files, "Number of PUT files"
            finally:
                c.close()

            c = cnx.cursor()
            try:
                c.execute(
                    "select count(*) from {name}".format(name=db_parameters["name"])
                )
                cnt = 0
                for rec in c:
                    cnt += rec[0]
                assert cnt == number_of_files * number_of_lines, "Number of rows"
            finally:
                c.close()
    finally:
        with conn_cnx(
            user=db_parameters["user"],
            account=db_parameters["account"],
            password=db_parameters["password"],
        ) as cnx:
            cnx.cursor().execute(
                "drop table if exists {table}".format(table=db_parameters["name"])
            )
