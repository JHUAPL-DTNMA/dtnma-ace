#
# Copyright (c) 2020-2025 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the AMM CODEC Engine (ACE) under the
# DTN Management Architecture (DTNMA) reference implementaton set from APL.
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
# Portions of this work were performed for the Jet Propulsion Laboratory,
# California Institute of Technology, sponsored by the United States Government
# under the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' ORM models for the ADM and its contents.
'''
from sqlalchemy import (
    Column, ForeignKey, Boolean, Integer, String, Date, DateTime, Text, PickleType
)
from sqlalchemy.orm import (
    declarative_base, relationship, declared_attr, Mapped
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import declarative_mixin, declared_attr

CURRENT_SCHEMA_VERSION = 20
''' Value of :attr:`SchemaVersion.version_num` '''

Base = declarative_base()

# pylint: disable=too-few-public-methods


class SchemaVersion(Base):
    ''' Identify the version of a DB. '''
    __tablename__ = "schema_version"
    version_num = Column(Integer, primary_key=True)

# These first classes are containers and are not explicitly bound to a
# parent ADM object.


@declarative_mixin
class CommonMixin:
    ''' Common module substatements. '''
    description = Column(String)


class MetadataItem(Base):
    ''' A single item of module, object, or substatement metadata. '''
    __tablename__ = "metadata_item"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey('metadata_list.id'))
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


class TypeUseMixin:
    ''' Common attributes for containing a :class:`typing` instance. '''
    typeobj = Column(PickleType)
    ''' An object derived from the :cls:`SemType` class. '''


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
    list_id = Column(Integer, ForeignKey('typename_list.id'))
    list = relationship("TypeNameList", back_populates="items")
    position = Column(Integer)
    ''' ordinal of this item in a :class:`TypeNameList` '''

    name = Column(String, nullable=False)
    ''' Unique name for the item, the type comes from :class:`TypeUseMixin` '''
    description = Column(String)
    ''' Arbitrary optional text '''

    default_value = Column(String)
    ''' Optional default value for parameter as text ARI. '''
    default_ari = Column(PickleType)
    ''' Resolved and decoded ARI for default_value. '''


class AdmSource(Base):
    ''' The original ADM file content and metadata from a successful load. '''
    __tablename__ = 'adm_source'

    id = Column(Integer, primary_key=True)
    ''' Unique ID of the row '''

    module = relationship('AdmModule')
    ''' Derived ADM module content '''

    abs_file_path = Column(String)
    ''' Fully resolved path from which the ADM was loaded '''
    last_modified = Column(DateTime)
    ''' Modified Time from the source file '''

    file_text = Column(Text)
    ''' Cached full file content. '''


class Organization(Base):
    ''' A namespace organization. '''
    __tablename__ = 'ns_org'
    id = Column(Integer, primary_key=True)
    ''' Unique ID of the row '''

    name = Column(String, index=True)
    ''' Normalized name of this organization '''
    enum = Column(Integer, index=True)
    ''' Enumeration for this organization '''


class AdmModule(Base):
    ''' The ADM itself with relations to its attributes and objects '''
    __tablename__ = "adm_module"
    id = Column(Integer, primary_key=True)
    ''' Unique ID of the row '''

    source_id = Column(Integer, ForeignKey('adm_source.id'))
    source = relationship(
        "AdmSource",
        back_populates='module',
        cascade="all, delete"
    )

    module_name = Column(String)
    ''' Original module name '''
    norm_name = Column(String, index=True)
    ''' Normalized module name (for searching) '''

    ns_org_name = Column(String, index=True)
    ''' Namespace organization name '''
    ns_org_enum = Column(Integer, index=True)
    ''' Organization enumeration from the module '''

    ns_model_name = Column(String, index=True)
    ''' Name of this model, in normalized form, within the organization '''
    ns_model_enum = Column(Integer, index=True)
    ''' Enumeration for this model within the organization '''

    metadata_id = Column(Integer, ForeignKey('metadata_list.id'), nullable=False)
    metadata_list = relationship(
        "MetadataList",
        cascade="all, delete"
    )

    revisions = relationship(
        "AdmRevision",
        back_populates="module",
        order_by='asc(AdmRevision.position)',
        cascade="all, delete"
    )

    @hybrid_property
    def latest_revision_date(self):
        return max(rev.date for rev in self.revisions)

    imports = relationship(
        "AdmImport",
        back_populates="module",
        order_by='asc(AdmImport.position)',
        cascade="all, delete"
    )
    feature = relationship(
        "Feature",
        back_populates="module",
        order_by='asc(Feature.position)',
        cascade="all, delete"
    )

    # references a list of contained objects
    typedef = relationship("Typedef",
                           back_populates="module",
                           order_by='asc(Typedef.position)',
                           cascade="all, delete")
    ident = relationship("Ident",
                         back_populates="module",
                         order_by='asc(Ident.position)',
                         cascade="all, delete")
    const = relationship("Const",
                         back_populates="module",
                         order_by='asc(Const.position)',
                         cascade="all, delete")
    ctrl = relationship("Ctrl",
                        back_populates="module",
                         order_by='asc(Ctrl.position)',
                        cascade="all, delete")
    edd = relationship("Edd",
                       back_populates="module",
                       order_by='asc(Edd.position)',
                       cascade="all, delete")
    oper = relationship("Oper",
                        back_populates="module",
                        order_by='asc(Oper.position)',
                        cascade="all, delete")
    var = relationship("Var",
                       back_populates="module",
                       order_by='asc(Var.position)',
                       cascade="all, delete")
    sbr = relationship("Sbr",
                       back_populates="module",
                       order_by='asc(Sbr.position)',
                       cascade="all, delete")
    tbr = relationship("Tbr",
                       back_populates="module",
                       order_by='asc(Tbr.position)',
                       cascade="all, delete")

    def __repr__(self):
        repr_attrs = ('id', 'norm_name')
        parts = [f"{attr}={getattr(self, attr)}" for attr in repr_attrs]
        return "ADM(" + ', '.join(parts) + ")"


class AdmRevision(Base, CommonMixin):
    ''' Each "revision" of an ADM '''
    __tablename__ = "adm_revision"
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="revisions")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text, indexed for sorting
    name = Column(String, index=True)
    # Parsed date
    date = Column(Date, index=True)


class AdmImport(Base, CommonMixin):
    ''' Each "import" of an ADM '''
    __tablename__ = "adm_import"
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="imports")
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
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="feature")
    # ordinal of this item in the module
    position = Column(Integer)

    # Unique name
    name = Column(String, nullable=False, index=True)


@declarative_mixin
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
    @declared_attr
    def parameters_id(self):
        return Column(Integer, ForeignKey('typename_list.id'))

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
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="typedef")


class Ident(Base, AdmObjMixin, ParamMixin):
    ''' Identity object (named, derived object) '''
    __tablename__ = "ident"
    id = Column(Integer, primary_key=True)
    ''' Unique ID of the row '''

    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    ''' ID of the file from which this came '''

    module = relationship("AdmModule", back_populates="ident")
    ''' Relationship to the :class:`AdmModule` '''

    abstract = Column(Boolean)
    ''' Explicit abstract marking '''

    bases = relationship(
        "IdentBase",
        order_by="IdentBase.position",
        collection_class=ordering_list('position'),
        cascade="all, delete"
    )


class IdentBase(Base):
    ''' Each Identity base reference '''
    __tablename__ = "ident_base"
    id = Column(Integer, primary_key=True)
    ''' Unique ID of the row '''

    @declared_attr
    def ident_id(self):
        return Column(Integer, ForeignKey('ident.id'))

    ''' ID of the file from which this came '''
    ident = relationship("Ident", back_populates="bases")
    ''' Relationship to the :class:`AdmModule` '''
    position = Column(Integer)
    ''' ordinal of this item in a :class:`TypeNameList` '''

    base_text = Column(String)
    ''' The object from which the parent Ident is derived as text ARI '''
    base_ari = Column(PickleType)
    ''' Resolved and decoded ARI '''


class Edd(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Externally Defined Data (EDD) '''
    __tablename__ = "edd"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="edd")


class Const(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Constant value (CONST) '''
    __tablename__ = "const"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="const")

    init_value = Column(String)
    ''' The initial and constant value as text ARI '''
    init_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`init_value`. '''


class Ctrl(Base, AdmObjMixin, ParamMixin):
    ''' Control '''
    __tablename__ = "ctrl"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="ctrl")

    result_id = Column(Integer, ForeignKey('typename_item.id'))
    result = relationship("TypeNameItem", foreign_keys=[result_id], cascade="all, delete")
    ''' Optional result descriptor. '''


class Oper(Base, AdmObjMixin, ParamMixin):
    ''' Operator (Oper) used in EXPR postfix '''
    __tablename__ = "oper"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="oper")

    operands_id = Column(Integer, ForeignKey('typename_list.id'), nullable=False)
    operands = relationship("TypeNameList",
                            foreign_keys=[operands_id],
                            cascade="all, delete")

    result_id = Column(Integer, ForeignKey('typename_item.id'), nullable=False)
    result = relationship("TypeNameItem", foreign_keys=[result_id], cascade="all, delete")


class Var(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Variable value (VAR)'''
    __tablename__ = "var"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="var")

    init_value = Column(String)
    ''' The initial value as text ARI '''
    init_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`init_value`. '''


class Sbr(Base, AdmObjMixin):
    ''' State Based Rule '''
    __tablename__ = "sbr"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="sbr")

    action_value = Column(String)
    ''' The action as text ARI '''
    action_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`action`. '''

    condition_value = Column(String)
    ''' The condition as text ARI '''
    condition_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`condition`. '''

    min_interval_value = Column(String)
    ''' The min_interval as text ARI '''
    min_interval_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`min_interval`. '''

    max_count = Column(Integer)
    init_enabled = Column(Boolean)


class Tbr(Base, AdmObjMixin):
    ''' Time Based Rule '''
    __tablename__ = "tbr"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # ID of the file from which this came
    @declared_attr
    def module_id(self):
        return Column(Integer, ForeignKey('adm_module.id'))

    # Relationship to the :class:`AdmModule`
    module = relationship("AdmModule", back_populates="tbr")

    action_value = Column(String)
    ''' The action as text ARI '''
    action_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`action`. '''

    period_value = Column(String)
    ''' The period as text ARI '''
    period_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`period`. '''

    start_value = Column(String)
    ''' The start as text ARI '''
    start_ari = Column(PickleType)
    ''' Resolved and decoded ARI for ivar:`start`. '''

    max_count = Column(Integer)
    init_enabled = Column(Boolean)
