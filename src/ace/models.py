#
# Copyright (c) 2020-2024 The Johns Hopkins University Applied Physics
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
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.orderinglist import ordering_list
import ace.ari


#: Value of :attr:`SchemaVersion.version_num`
CURRENT_SCHEMA_VERSION = 12


Base = declarative_base()


# pylint: disable=too-few-public-methods

class SchemaVersion(Base):
    ''' Identify the version of a DB. '''
    __tablename__ = "schema_version"
    version_num = Column(Integer, primary_key=True)

# These first classes are containers and are not explicitly bound to a
# parent ADM object.


class TypeNameList(Base):
    ''' A list of typed, named items (e.g. parameters or columns) '''
    __tablename__ = "typename_list"
    ''' Logical list of type/name items for an ADM object.
    Used by CTRL and EDD for parameters and TBLT for columns.

    There is no explicit relationship to the object which contains this type.
    '''
    id = Column(Integer, primary_key=True)

    items = relationship("TypeNameItem", order_by="TypeNameItem.position",
                         collection_class=ordering_list('position'), cascade="all, delete")


class TypeNameItem(Base):
    ''' Each item within a TypeNameList '''
    __tablename__ = "typename_item"
    id = Column(Integer, primary_key=True)

    #: Containing list
    list_id = Column(Integer, ForeignKey("typename_list.id"))
    list = relationship("TypeNameList", back_populates="items")
    #: ordinal of this parameter in a TypeNameList
    position = Column(Integer)

    type = Column(String)
    name = Column(String, nullable=False)


class ARI(Base):
    ''' A single non-literal ARI '''
    __tablename__ = "ari"
    id = Column(Integer, primary_key=True)

    #: Optional containing AC
    list_id = Column(Integer, ForeignKey("ac.id"))
    #: Relationship to the :class:`AC`
    list = relationship("AC", back_populates="items")
    #: ordinal of this parameter in an AC (if part of an AC)
    position = Column(Integer)

    #: Namespace
    ns = Column(String)
    #: Name
    nm = Column(String)
    #: Optional parameters
    ap = relationship("AriAP", order_by="AriAP.position",
                      collection_class=ordering_list('position'),
                      cascade="all, delete")

class AriAP(Base):
    ''' Defining each parameter used by an ARI '''
    __tablename__ = "ari_ap"
    id = Column(Integer, primary_key=True)
    #: ID of the Oper for which this is a parameter
    ari_id = Column(Integer, ForeignKey("ari.id"))
    #: Relationship to the parent :class:`Oper`
    ari = relationship("ARI", back_populates="ap")
    #: ordinal of this parameter in an ARI list
    position = Column(Integer)

    type = Column(String)
    value = Column(String)

class AC(Base):
    ''' An ARI Collection (AC).
    Used by macros to define the action, used by reports to define the contents.

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "ac"
    id = Column(Integer, primary_key=True)

    items = relationship("ARI", order_by="ARI.position",
                         collection_class=ordering_list('position'),
                         cascade="all, delete")


class Expr(Base):
    ''' Expression (EXPR) '''
    __tablename__ = "expr"
    id = Column(Integer, primary_key=True)

    #: Result type of the expression
    type = Column(String)
    #: The AC defining the postfix expression
    postfix_id = Column(Integer, ForeignKey('ac.id'))
    #: Relationship to the :class:`AC`
    postfix = relationship("AC")


class AdmFile(Base):
    ''' The ADM file itself and its source (filesystem) metadata '''
    __tablename__ = "admfile"

    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: Fully resolved path from which the ADM was loaded
    abs_file_path = Column(String)
    #: Modified Time from the source file
    last_modified = Column(DateTime)

    #: Normalized ADM name (for searching)
    norm_name = Column(String, index=True)
    #: Normalized ADM namespace (for searching)
    norm_namespace = Column(String, index=True)
    #: non normalized namespace 
    adm_ns = Column(String, index=True)

    #: Enumeration for this ADM
    enum = Column(Integer, index=True)

    uses = relationship("AdmUses", back_populates="admfile",
                        order_by='asc(AdmUses.position)',
                        cascade="all, delete")

    # references a list of contained objects
    mdat = relationship("Mdat", back_populates="admfile",
                        order_by='asc(Mdat.enum)',
                        cascade="all, delete")
    const = relationship("Const", back_populates="admfile",
                         order_by='asc(Const.enum)',
                         cascade="all, delete")
    ctrl = relationship("Ctrl", back_populates="admfile",
                        cascade="all, delete")
    edd = relationship("Edd", back_populates="admfile",
                       order_by='asc(Edd.enum)',
                       cascade="all, delete")
    mac = relationship("Mac", back_populates="admfile",
                       order_by='asc(Mac.enum)',
                       cascade="all, delete")
    oper = relationship("Oper", back_populates="admfile",
                        order_by='asc(Oper.enum)',
                        cascade="all, delete")
    rptt = relationship("Rptt", back_populates="admfile",
                        order_by='asc(Rptt.enum)',
                        cascade="all, delete")
    tblt = relationship("Tblt", back_populates="admfile",
                        order_by='asc(Tblt.enum)',
                        cascade="all, delete")
    var = relationship("Var", back_populates="admfile",
                       order_by='asc(Var.enum)',
                       cascade="all, delete")

    def __repr__(self):
        repr_attrs = ('id', 'norm_name', 'abs_file_path', 'last_modified')
        parts = [f"{attr}={getattr(self, attr)}" for attr in repr_attrs]
        return "ADM(" + ', '.join(parts) + ")"


class AdmUses(Base):
    ''' Each "uses" of an ADM '''
    __tablename__ = "adm_uses"
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="uses")
    #: ordinal of this item in the list
    position = Column(Integer)

    #: Original exact text
    namespace = Column(String)

    #: Normalized text for searching    
    norm_namespace = Column(String, index=True)


class AdmObjMixin:
    ''' Common attributes of an ADM-defined object. '''
    #: Unique name (within a section)
    name = Column(String, nullable=False)
    #: Arbitrary optional text
    description = Column(String)

    #: Normalized object name (for searching)
    norm_name = Column(String, index=True)
    #: Enumeration for this ADM
    enum = Column(Integer, index=True)


# These following classes are all proper ADM top-level object sections.

class Mdat(Base, AdmObjMixin):
    ''' Metadata about the ADM '''
    __tablename__ = "mdat"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="mdat")

    #: Not really used
    type = Column(String)
    #: The metadata value text
    value = Column(String, nullable=False)


class Edd(Base, AdmObjMixin):
    ''' Externally Defined Data (EDD) '''
    __tablename__ = "edd"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="edd")

    type = Column(String, nullable=False)
    #: Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")


class Const(Base, AdmObjMixin):
    ''' Constant value (CONST) '''
    __tablename__ = "const"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="const")

    type = Column(String)
    value = Column(String)


class Ctrl(Base, AdmObjMixin):
    ''' Control '''
    __tablename__ = "ctrl"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="ctrl")

    #: Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")


class Mac(Base, AdmObjMixin):
    ''' Macro (MAC) - an ordered collection of Controls or of other Macros '''
    __tablename__ = "mac"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="mac")

    #: Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")

    #: Reference to the EXPR action of this macro
    action_id = Column(Integer, ForeignKey("ac.id"), nullable=False)
    #: Relationship to the :class:`AC` object
    action = relationship("AC")


class Oper(Base, AdmObjMixin):
    ''' Operator (Oper) used in EXPR postfix '''
    __tablename__ = "oper"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="oper")

    result_type = Column(String)
    in_type = relationship("OperParm", order_by="OperParm.position",
                           collection_class=ordering_list('position'),
                           cascade="all, delete")


class OperParm(Base):
    ''' Defining each parameter used by an Oper '''
    __tablename__ = "oper_parm"
    id = Column(Integer, primary_key=True)
    #: ID of the Oper for which this is a parameter
    oper_id = Column(Integer, ForeignKey("oper.id"))
    #: Relationship to the parent :class:`Oper`
    oper = relationship("Oper", back_populates="in_type")
    #: ordinal of this parameter in an Oper
    position = Column(Integer)

    type = Column(String)


class Rptt(Base, AdmObjMixin):
    ''' Report Template (RPTT)'''
    __tablename__ = "rptt"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="rptt")

    #: Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")

    #: Items present in the report
    definition_id = Column(Integer, ForeignKey('ac.id'), nullable=False)
    definition = relationship("AC")


class Tblt(Base, AdmObjMixin):
    ''' Table Template (TBLT)'''
    __tablename__ = "tblt"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="tblt")

    #: Columns present in the table
    columns_id = Column(Integer, ForeignKey('typename_list.id'), nullable=False)
    columns = relationship("TypeNameList", cascade="all, delete")


class Var(Base, AdmObjMixin):
    ''' Variable value (VAR)'''
    __tablename__ = "var"
    #: Unique ID of the row
    id = Column(Integer, primary_key=True)
    #: ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    #: Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="var")

    type = Column(String, nullable=False)
    initializer_id = Column(Integer, ForeignKey('expr.id'))
    initializer = relationship("Expr")

