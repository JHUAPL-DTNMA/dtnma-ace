#
# Copyright (c) 2023 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the Asynchronous Network Managment System (ANMS).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This work was performed for the Jet Propulsion Laboratory, California
# Institute of Technology, sponsored by the United States Government under
# the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' ORM models for the ADM and its contents.
'''
import logging
from typing import List
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, PickleType
from sqlalchemy.orm import (
    declarative_base, relationship, declared_attr, Mapped
)
from sqlalchemy.orm.session import object_session
from sqlalchemy.ext.orderinglist import ordering_list
from ace.typing import BUILTINS, SemType, TypeUse

LOGGER = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 13
''' Value of :attr:`SchemaVersion.version_num` '''

Base = declarative_base()

# pylint: disable=too-few-public-methods


class SchemaVersion(Base):
    ''' Identify the version of a DB. '''
    __tablename__ = "schema_version"
    version_num = Column(Integer, primary_key=True)

# These first classes are containers and are not explicitly bound to a
# parent ADM object.


class CommonMixin:
    ''' Common module substatements. '''
    description = Column(String)


class MetadataItem(Base):
    ''' A single item of module, object, or substatement metadata. '''
    __tablename__ = "metadata_item"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("metadata_list.id"))
    list = relationship("MetadataList", back_populates="items")

    name = Column(String, nullable=False)
    arg = Column(String, nullable=False)


class MetadataList(Base):
    ''' A list of named metadata items.

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "metadata_list"
    id = Column(Integer, primary_key=True)

    items = relationship(
        "MetadataItem",
        order_by="MetadataItem.name",
        collection_class=ordering_list('name'),
        cascade="all, delete"
    )


class TypeBindingError(RuntimeError):

    def __init__(self, msg:str, badtypes:List):
        super().__init__(msg)
        self.badtypes = badtypes


class TypeUseMixin:
    ''' Common attributes for containing a :class:`typing` instance. '''
    typeobj = Column(PickleType)
    ''' An object derived from the :cls:`SemType` class. '''

    def typeobj_bound(self, adm:'AdmFile') -> SemType:
        ''' Bind references to external BaseType objects from type names.

        :return: The :ivar:`typeobj` with all type references bound.
        :raise TypeBindingError: If any required types are missing.
        '''
        typeobj = self.typeobj
        if typeobj is None:
            return None

        db_sess = object_session(self)
        badtype = set()

        def visitor(obj):
            ''' Check cross-referenced type names. '''
            if isinstance(obj, TypeUse):
                if obj.type_ns is None:
                    # Search own ADM first, then built-ins
                    found = (
                        db_sess.query(Typedef).join(AdmFile)
                        .filter(
                            Typedef.admfile == adm,
                            Typedef.norm_name == obj.type_name
                        )
                    ).one_or_none()
                    if found:
                        # recursive binding
                        obj.base = found.typeobj_bound(adm)
                    elif obj.type_name in BUILTINS:
                        obj.base = BUILTINS[obj.type_name]
                    else:
                        badtype.add(obj.type_name)
                else:
                    other_adm = (
                        db_sess.query(AdmFile)
                        .filter(
                            AdmFile.norm_name == obj.type_ns
                        )
                    ).one_or_none()
                    if other_adm is None:
                        badtype.add((obj.type_ns, obj.type_name))
                        return

                    found = (
                        db_sess.query(Typedef).join(AdmFile)
                        .filter(
                            Typedef.admfile == other_adm,
                            Typedef.norm_name == obj.type_name
                        )
                    ).one_or_none()
                    if found is None:
                        badtype.add((obj.type_ns, obj.type_name))
                    else:
                        # recursive binding
                        obj.base = found.typeobj_bound(other_adm)
                LOGGER.debug('bound %s:%s as %s', obj.type_ns, obj.type_name, obj.base)

        typeobj.visit(visitor)
        if badtype:
            raise TypeBindingError(f'Missing types to bind to: {badtype}', badtype)

        return typeobj


class TypeNameList(Base):
    ''' A list of typed, named items (e.g. parameters or columns).

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "typename_list"
    id = Column(Integer, primary_key=True)

    items = relationship(
        "TypeNameItem",
        order_by="TypeNameItem.position",
        collection_class=ordering_list('position'),
        cascade="all, delete"
    )


class TypeNameItem(Base, TypeUseMixin):
    ''' Each item within a TypeNameList '''
    __tablename__ = "typename_item"
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("typename_list.id"))
    list = relationship("TypeNameList", back_populates="items")
    position = Column(Integer)
    ''' ordinal of this item in a :class:`TypeNameList` '''

    name = Column(String, nullable=False)
    ''' Unique name for the item, the type comes from :class:`TypeUseMixin` '''
    description = Column(String)
    ''' Arbitrary optional text '''


class AdmFile(Base):
    ''' The ADM file itself and its source (filesystem) metadata '''
    __tablename__ = "admfile"

    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # Fully resolved path from which the ADM was loaded
    abs_file_path = Column(String)
    # Modified Time from the source file
    last_modified = Column(DateTime)

    # Normalized ADM name (for searching)
    name = Column(String)
    # Normalized ADM name (for searching)
    norm_name = Column(String, index=True)
    # Enumeration for this ADM
    enum = Column(Integer, index=True)

    metadata_id = Column(Integer, ForeignKey('metadata_list.id'), nullable=False)
    metadata_list = relationship(
        "MetadataList",
        cascade="all, delete"
    )

    revisions = relationship(
        "AdmRevision",
        back_populates="admfile",
        order_by='asc(AdmRevision.position)',
        cascade="all, delete"
    )

    imports = relationship(
        "AdmImport",
        back_populates="admfile",
        order_by='asc(AdmImport.position)',
        cascade="all, delete"
    )
    feature = relationship(
        "Feature",
        back_populates="admfile",
        order_by='asc(Feature.position)',
        cascade="all, delete"
    )

    # references a list of contained objects
    typedef = relationship("Typedef",
                           back_populates="admfile",
                           order_by='asc(Typedef.position)',
                           cascade="all, delete")
    const = relationship("Const",
                         back_populates="admfile",
                         order_by='asc(Const.position)',
                         cascade="all, delete")
    ctrl = relationship("Ctrl",
                        back_populates="admfile",
                         order_by='asc(Ctrl.position)',
                        cascade="all, delete")
    edd = relationship("Edd",
                       back_populates="admfile",
                       order_by='asc(Edd.position)',
                       cascade="all, delete")
    oper = relationship("Oper",
                        back_populates="admfile",
                        order_by='asc(Oper.position)',
                        cascade="all, delete")
    var = relationship("Var",
                       back_populates="admfile",
                       order_by='asc(Var.position)',
                       cascade="all, delete")

    def __repr__(self):
        repr_attrs = ('id', 'norm_name', 'abs_file_path', 'last_modified')
        parts = [f"{attr}={getattr(self, attr)}" for attr in repr_attrs]
        return "ADM(" + ', '.join(parts) + ")"


class AdmRevision(Base, CommonMixin):
    ''' Each "revision" of an ADM '''
    __tablename__ = "adm_revision"
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="revisions")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text, indexed for sorting
    name = Column(String, index=True)


class AdmImport(Base, CommonMixin):
    ''' Each "import" of an ADM '''
    __tablename__ = "adm_import"
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="imports")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text
    name = Column(String)
    # Prefix within the module
    prefix = Column(String)


class Feature(Base, CommonMixin):
    ''' Feature definition, which is a module-only object not an AMM object. '''
    __tablename__ = "feature"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="feature")
    # ordinal of this item in the module
    position = Column(Integer)

    # Unique name
    name = Column(String, nullable=False, index=True)


class AdmObjMixin(CommonMixin):
    ''' Common attributes of an ADM-defined object. '''
    # ordinal of this item in the module
    position = Column(Integer)

    # Unique name (within a section)
    name = Column(String, nullable=False)
    # Normalized object name (for searching)
    norm_name = Column(String, index=True)

    # Enumeration for this ADM
    enum = Column(Integer, index=True)

    if_feature_expr = Column(PickleType)
    ''' Feature-matching parsed expression.
    See :func:`pyang.syntax.parse_if_feature_expr`.
    '''


class ParamMixin:
    ''' Attributes for formal parameters of an object. '''
    # Parameters of this object
    parameters_id = Column(Integer, ForeignKey("typename_list.id"))

    # Relationship to the :class:`TypeNameList`
    @declared_attr
    def parameters(self) -> Mapped["TypeNameList"]:
        return relationship(
            "TypeNameList",
            foreign_keys=[self.parameters_id],
            cascade="all, delete"
        )

# These following classes are all proper ADM top-level object sections.


class Typedef(Base, AdmObjMixin, TypeUseMixin):
    ''' Type definition (named semantic type) '''
    __tablename__ = "typedef"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="typedef")


class Edd(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Externally Defined Data (EDD) '''
    __tablename__ = "edd"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="edd")


class Const(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Constant value (CONST) '''
    __tablename__ = "const"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="const")

    init_value = Column(String)
    ''' The initial and constant value as text ARI '''


class Ctrl(Base, AdmObjMixin, ParamMixin):
    ''' Control '''
    __tablename__ = "ctrl"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="ctrl")

    result_id = Column(Integer, ForeignKey("typename_item.id"))
    result = relationship("TypeNameItem", foreign_keys=[result_id], cascade="all, delete")
    ''' Optional result descriptor. '''


class Oper(Base, AdmObjMixin, ParamMixin):
    ''' Operator (Oper) used in EXPR postfix '''
    __tablename__ = "oper"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="oper")

    operands_id = Column(Integer, ForeignKey('typename_list.id'), nullable=False)
    operands = relationship("TypeNameList",
                            foreign_keys=[operands_id],
                            cascade="all, delete")

    result_id = Column(Integer, ForeignKey("typename_item.id"), nullable=False)
    result = relationship("TypeNameItem", foreign_keys=[result_id], cascade="all, delete")


class Var(Base, AdmObjMixin, TypeUseMixin):
    ''' Variable value (VAR)'''
    __tablename__ = "var"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="var")

    init_value = Column(String)
    ''' The initial and constant value as text ARI '''
