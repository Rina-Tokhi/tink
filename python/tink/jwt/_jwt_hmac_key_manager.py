# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A JWT HMAC key manager."""

from __future__ import absolute_import
from __future__ import division
# Placeholder for import for type annotations
from __future__ import print_function

from typing import Text, Type

from tink.proto import jwt_hmac_pb2
from tink.proto import tink_pb2
from tink import core
from tink.cc.pybind import tink_bindings
from tink.jwt import _jwt_error
from tink.jwt import _jwt_format
from tink.jwt import _jwt_mac
from tink.jwt import _jwt_validator
from tink.jwt import _raw_jwt
from tink.jwt import _verified_jwt

_JWT_HMAC_KEY_TYPE = 'type.googleapis.com/google.crypto.tink.JwtHmacKey'

_ALGORITHM_STRING = {
    jwt_hmac_pb2.HS256: 'HS256',
    jwt_hmac_pb2.HS384: 'HS384',
    jwt_hmac_pb2.HS512: 'HS512'
}


class _JwtHmac(_jwt_mac.JwtMac):
  """Interface for authenticating and verifying JWT with JWS MAC."""

  def __init__(self, cc_mac: tink_bindings.Mac, algorithm: Text):
    self._cc_mac = cc_mac
    self._algorithm = algorithm

  @core.use_tink_errors
  def _compute_mac(self, data: bytes) -> bytes:
    return self._cc_mac.compute_mac(data)

  @core.use_tink_errors
  def _verify_mac(self, mac_value: bytes, data: bytes) -> None:
    self._cc_mac.verify_mac(mac_value, data)

  def compute_mac_and_encode(self, raw_jwt: _raw_jwt.RawJwt) -> Text:
    """Computes a MAC and encodes the token."""
    unsigned = _jwt_format.create_unsigned_compact(self._algorithm,
                                                   raw_jwt.json_payload())
    return _jwt_format.create_signed_compact(unsigned,
                                             self._compute_mac(unsigned))

  def verify_mac_and_decode(
      self, compact: Text,
      validator: _jwt_validator.JwtValidator) -> _verified_jwt.VerifiedJwt:
    """Verifies, validates and decodes a MACed compact JWT token."""
    parts = _jwt_format.split_signed_compact(compact)
    unsigned_compact, json_header, json_payload, mac = parts
    self._verify_mac(mac, unsigned_compact)
    header = _jwt_format.json_loads(json_header)
    _jwt_format.validate_header(header, self._algorithm)
    raw_jwt = _raw_jwt.RawJwt.from_json(json_payload)
    _jwt_validator.validate(validator, raw_jwt)
    return _verified_jwt.VerifiedJwt._create(raw_jwt)  # pylint: disable=protected-access


class MacCcToPyJwtMacKeyManager(core.KeyManager[_jwt_mac.JwtMac]):
  """Transforms C++ KeyManager into a Python KeyManager."""

  def __init__(self):
    self._cc_key_manager = tink_bindings.MacKeyManager.from_cc_registry(
        'type.googleapis.com/google.crypto.tink.JwtHmacKey')

  def primitive_class(self) -> Type[_jwt_mac.JwtMac]:
    return _jwt_mac.JwtMac

  @core.use_tink_errors
  def primitive(self, key_data: tink_pb2.KeyData) -> _jwt_mac.JwtMac:
    if key_data.type_url != _JWT_HMAC_KEY_TYPE:
      raise _jwt_error.JwtInvalidError('Invalid key data key type')
    jwt_hmac_key = jwt_hmac_pb2.JwtHmacKey.FromString(key_data.value)
    algorithm = _ALGORITHM_STRING[jwt_hmac_key.algorithm]
    cc_mac = self._cc_key_manager.primitive(key_data.SerializeToString())
    return _JwtHmac(cc_mac, algorithm)

  def key_type(self) -> Text:
    return self._cc_key_manager.key_type()

  @core.use_tink_errors
  def new_key_data(self,
                   key_template: tink_pb2.KeyTemplate) -> tink_pb2.KeyData:
    data = self._cc_key_manager.new_key_data(key_template.SerializeToString())
    return tink_pb2.KeyData.FromString(data)


def register():
  tink_bindings.register_jwt()
  core.Registry.register_key_manager(
      MacCcToPyJwtMacKeyManager(), new_key_allowed=True)
