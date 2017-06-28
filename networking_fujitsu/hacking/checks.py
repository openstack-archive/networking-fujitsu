# Copyright (c) 2017 OpenStack Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


def no_translate_logs(logical_line, filename):
    """Check for log translation.

    Starting with the Pike series, OpenStack no longer supports log
    translation.
    Since _LI, _LW, _LE, _LC have been removed, we just need to check _().
    """
    if (logical_line.startswith("LOG.debug(_(") or
            logical_line.startswith("LOG.info(_(") or
            logical_line.startswith("LOG.warning(_(") or
            logical_line.startswith("LOG.error(_(") or
            logical_line.startswith("LOG.exception(_(") or
            logical_line.startswith("LOG.critical(_(")):
        yield(0, "NF301: Don't translate log messages")


def factory(register):
    register(no_translate_logs)
