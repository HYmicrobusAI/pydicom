# test_filewriter.py
"""unittest cases for pydicom.filewriter module"""
# Copyright (c) 2008-2012 Darcy Mason
# This file is part of pydicom, released under a modified MIT license.
#    See the file license.txt included with this distribution, also
#    available at https://github.com/darcymason/pydicom

from copy import deepcopy
from datetime import date, datetime, time
from io import BytesIO
import os
import os.path
import sys
from tempfile import TemporaryFile

have_dateutil = True
try:
    from dateutil.tz import tzoffset
except ImportError:
    have_dateutil = False
import unittest
try:
    unittest.TestCase.assertSequenceEqual
except AttributeError:
    try:
        import unittest2 as unittest
    except ImportError:
        print("unittest2 is required for testing in python2.6")

from pydicom import config
from pydicom.dataset import Dataset, FileDataset
from pydicom.dataelem import DataElement
from pydicom.filebase import DicomBytesIO
from pydicom.filereader import read_file, read_dataset
from pydicom.filewriter import (write_data_element, write_dataset,
                                correct_ambiguous_vr, write_file_meta_info)
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.uid import ImplicitVRLittleEndian, ExplicitVRBigEndian
from pydicom.util.hexutil import hex2bytes, bytes2hex
from pydicom.valuerep import DA, DT, TM

test_dir = os.path.dirname(__file__)
test_files = os.path.join(test_dir, 'test_files')
testcharset_dir = os.path.join(test_dir, 'charset_files')

rtplan_name = os.path.join(test_files, "rtplan.dcm")
rtdose_name = os.path.join(test_files, "rtdose.dcm")
ct_name = os.path.join(test_files, "CT_small.dcm")
mr_name = os.path.join(test_files, "MR_small.dcm")
jpeg_name = os.path.join(test_files, "JPEG2000.dcm")
no_ts = os.path.join(test_files, "meta_missing_tsyntax.dcm")
datetime_name = mr_name

unicode_name = os.path.join(testcharset_dir, "chrH31.dcm")
multiPN_name = os.path.join(testcharset_dir, "chrFrenMulti.dcm")


def files_identical(a, b):
    """Return a tuple (file a == file b, index of first difference)"""
    with open(a, "rb") as A:
        with open(b, "rb") as B:
            a_bytes = A.read()
            b_bytes = B.read()

    return bytes_identical(a_bytes, b_bytes)

def bytes_identical(a_bytes, b_bytes):
    """Return a tuple (bytes a == bytes b, index of first difference)"""
    if len(a_bytes) != len(b_bytes):
        return False, min([len(a_bytes), len(b_bytes)])
    elif a_bytes == b_bytes:
        return True, 0     # True, dummy argument
    else:
        pos = 0
        while a_bytes[pos] == b_bytes[pos]:
            pos += 1
        return False, pos   # False if not identical, position of 1st diff


class WriteFileTests(unittest.TestCase):
    def setUp(self):
        self.file_out = TemporaryFile('w+b')

    def compare(self, in_filename, decode=False):
        """Read Dataset from `in_filename`, write Dataset to file, then compare."""
        with open(in_filename, 'rb') as f:
            bytes_in = BytesIO(f.read())
            bytes_in.seek(0)

        ds = read_file(bytes_in)
        ds.save_as(self.file_out)
        self.file_out.seek(0)
        bytes_out = BytesIO(self.file_out.read())
        bytes_in.seek(0)
        bytes_out.seek(0)
        same, pos = bytes_identical(bytes_in.getvalue(), bytes_out.getvalue())
        self.assertTrue(same, "Read bytes is not identical to written bytes - "
                              "first difference at 0x%x" % pos)

    def compare_bytes(self, bytes_in, bytes_out):
        """Compare two bytestreams for equality"""
        same, pos = bytes_identical(bytes_in, bytes_out)
        self.assertTrue(same, "Bytestreams are not identical - first "
                        "difference at 0x%x" %pos)

    def testRTPlan(self):
        """Input file, write back and verify them identical (RT Plan file)"""
        self.compare(rtplan_name)

    def testRTDose(self):
        """Input file, write back and verify them identical (RT Dose file)"""
        self.compare(rtdose_name)

    def testCT(self):
        """Input file, write back and verify them identical (CT file)....."""
        self.compare(ct_name)

    def testMR(self):
        """Input file, write back and verify them identical (MR file)....."""
        self.compare(mr_name)

    def testUnicode(self):
        """Ensure decoded string DataElements are written to file properly"""
        self.compare(unicode_name, decode=True)

    def testMultiPN(self):
        """Ensure multiple Person Names are written to the file correctly."""
        self.compare(multiPN_name, decode=True)

    def testJPEG2000(self):
        """Input file, write back and verify them identical (JPEG2K file)."""
        self.compare(jpeg_name)

    def testListItemWriteBack(self):
        """Change item in a list and confirm it is written to file      .."""
        DS_expected = 0
        CS_expected = "new"
        SS_expected = 999
        ds = read_file(ct_name)
        ds.ImagePositionPatient[2] = DS_expected
        ds.ImageType[1] = CS_expected
        ds[(0x0043, 0x1012)].value[0] = SS_expected
        ds.save_as(self.file_out)
        self.file_out.seek(0)
        # Now read it back in and check that the values were changed
        ds = read_file(self.file_out)
        self.assertTrue(ds.ImageType[1] == CS_expected,
                        "Item in a list not written correctly to file (VR=CS)")
        self.assertTrue(ds[0x00431012].value[0] == SS_expected,
                        "Item in a list not written correctly to file (VR=SS)")
        self.assertTrue(ds.ImagePositionPatient[2] == DS_expected,
                        "Item in a list not written correctly to file (VR=DS)")

    def testwrite_short_uid(self):
        ds = read_file(rtplan_name)
        ds.SOPInstanceUID = "1.2"
        ds.save_as(self.file_out)
        self.file_out.seek(0)
        ds = read_file(self.file_out)
        self.assertEqual(ds.SOPInstanceUID, "1.2")

    def test_write_no_ts(self):
        """Test reading a file with no ts and writing it out identically."""
        ds = read_file(no_ts)
        ds.save_as(self.file_out, write_like_original=True)
        self.file_out.seek(0)
        with open(no_ts, 'rb') as ref_file:
            written_bytes = self.file_out.read()
            read_bytes = ref_file.read()
            self.compare_bytes(read_bytes, written_bytes)

    def test_write_double_filemeta(self):
        """Test writing file meta from Dataset doesn't work"""
        ds = read_file(ct_name)
        ds.TransferSyntaxUID = '1.1'
        self.assertRaises(ValueError, ds.save_as, self.file_out)


@unittest.skipIf(not have_dateutil, "Need python-dateutil installed for these tests")
class ScratchWriteDateTimeTests(WriteFileTests):
    """Write and reread simple or multi-value DA/DT/TM data elements"""
    def setUp(self):
        config.datetime_conversion = True
        self.file_out = TemporaryFile('w+b')

    def tearDown(self):
        config.datetime_conversion = False

    def test_multivalue_DA(self):
        """Write DA/DT/TM data elements.........."""
        multi_DA_expected = (date(1961, 8, 4), date(1963, 11, 22))
        DA_expected = date(1961, 8, 4)
        tzinfo = tzoffset('-0600', -21600)
        multi_DT_expected = (datetime(1961, 8, 4),
                             datetime(1963, 11, 22, 12, 30, 0, 0,
                                      tzoffset('-0600', -21600)))
        multi_TM_expected = (time(1, 23, 45), time(11, 11, 11))
        TM_expected = time(11, 11, 11, 1)
        ds = read_file(datetime_name)
        # Add date/time data elements
        ds.CalibrationDate = MultiValue(DA, multi_DA_expected)
        ds.DateOfLastCalibration = DA(DA_expected)
        ds.ReferencedDateTime = MultiValue(DT, multi_DT_expected)
        ds.CalibrationTime = MultiValue(TM, multi_TM_expected)
        ds.TimeOfLastCalibration = TM(TM_expected)
        ds.save_as(self.file_out)
        self.file_out.seek(0)
        # Now read it back in and check the values are as expected
        ds = read_file(self.file_out)
        self.assertSequenceEqual(multi_DA_expected, ds.CalibrationDate, "Multiple dates not written correctly (VR=DA)")
        self.assertEqual(DA_expected, ds.DateOfLastCalibration, "Date not written correctly (VR=DA)")
        self.assertSequenceEqual(multi_DT_expected, ds.ReferencedDateTime, "Multiple datetimes not written correctly (VR=DT)")
        self.assertSequenceEqual(multi_TM_expected, ds.CalibrationTime, "Multiple times not written correctly (VR=TM)")
        self.assertEqual(TM_expected, ds.TimeOfLastCalibration, "Time not written correctly (VR=DA)")


class WriteDataElementTests(unittest.TestCase):
    """Attempt to write data elements has the expected behaviour"""
    def setUp(self):
        # Create a dummy (in memory) file to write to
        self.f1 = DicomBytesIO()
        self.f1.is_little_endian = True
        self.f1.is_implicit_VR = True

    @staticmethod
    def encode_element(elem, is_implicit_VR=True, is_little_endian=True):
        """Return the encoded `elem`.

        Parameters
        ----------
        elem : pydicom.dataelem.DataElement
            The element to encode
        is_implicit_VR : bool
            Encode using implicit VR, default True
        is_little_endian : bool
            Encode using little endian, default True

        Returns
        -------
        str or bytes
            The encoded element as str (python2) or bytes (python3)
        """
        with DicomBytesIO() as fp:
            fp.is_implicit_VR = is_implicit_VR
            fp.is_little_endian = is_little_endian
            write_data_element(fp, elem)
            return fp.parent.getvalue()

    def test_empty_AT(self):
        """Write empty AT correctly.........."""
        # Was issue 74
        data_elem = DataElement(0x00280009, "AT", [])
        expected = hex2bytes((
            " 28 00 09 00"   # (0028,0009) Frame Increment Pointer
            " 00 00 00 00"   # length 0
        ))
        write_data_element(self.f1, data_elem)
        got = self.f1.getvalue()
        msg = ("Did not write zero-length AT value correctly. "
               "Expected %r, got %r") % (bytes2hex(expected), bytes2hex(got))
        msg = "%r %r" % (type(expected), type(got))
        msg = "'%r' '%r'" % (expected, got)
        self.assertEqual(expected, got, msg)

    def test_write_OD_implicit_little(self):
        """Test writing elements with VR of OD works correctly."""
        # VolumetricCurvePoints
        bytestring = b'\x00\x01\x02\x03\x04\x05\x06\x07' \
                     b'\x01\x01\x02\x03\x04\x05\x06\x07'
        elem = DataElement(0x0070150d, 'OD', bytestring)
        encoded_elem = self.encode_element(elem)
        # Tag pair (0070, 150d): 70 00 0d 15
        # Length (16): 10 00 00 00
        #             | Tag          |   Length      |    Value ->
        ref_bytes = b'\x70\x00\x0d\x15\x10\x00\x00\x00' + bytestring
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = b''
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x70\x00\x0d\x15\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_OD_explicit_little(self):
        """Test writing elements with VR of OD works correctly.

        Elements with a VR of 'OD' use the newer explicit VR
        encoding (see PS3.5 Section 7.1.2).
        """
        # VolumetricCurvePoints
        bytestring = b'\x00\x01\x02\x03\x04\x05\x06\x07' \
                     b'\x01\x01\x02\x03\x04\x05\x06\x07'
        elem = DataElement(0x0070150d, 'OD', bytestring)
        encoded_elem = self.encode_element(elem, False, True)
        # Tag pair (0070, 150d): 70 00 0d 15
        # VR (OD): \x4f\x44
        # Reserved: \x00\x00
        # Length (16): \x10\x00\x00\x00
        #             | Tag          | VR    | Rsrvd |   Length      |    Value ->
        ref_bytes = b'\x70\x00\x0d\x15\x4f\x44\x00\x00\x10\x00\x00\x00' + bytestring
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = b''
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x70\x00\x0d\x15\x4f\x44\x00\x00\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_OL_implicit_little(self):
        """Test writing elements with VR of OL works correctly."""
        # TrackPointIndexList
        bytestring = b'\x00\x01\x02\x03\x04\x05\x06\x07' \
                     b'\x01\x01\x02\x03'
        elem = DataElement(0x00660129, 'OL', bytestring)
        encoded_elem = self.encode_element(elem)
        # Tag pair (0066, 0129): 66 00 29 01
        # Length (12): 0c 00 00 00
        #             | Tag          |   Length      |    Value ->
        ref_bytes = b'\x66\x00\x29\x01\x0c\x00\x00\x00' + bytestring
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = b''
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x66\x00\x29\x01\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_OL_explicit_little(self):
        """Test writing elements with VR of OL works correctly.

        Elements with a VR of 'OL' use the newer explicit VR
        encoding (see PS3.5 Section 7.1.2).
        """
        # TrackPointIndexList
        bytestring = b'\x00\x01\x02\x03\x04\x05\x06\x07' \
                     b'\x01\x01\x02\x03'
        elem = DataElement(0x00660129, 'OL', bytestring)
        encoded_elem = self.encode_element(elem, False, True)
        # Tag pair (0066, 0129): 66 00 29 01
        # VR (OL): \x4f\x4c
        # Reserved: \x00\x00
        # Length (12): 0c 00 00 00
        #             | Tag          | VR    | Rsrvd |   Length      |    Value ->
        ref_bytes = b'\x66\x00\x29\x01\x4f\x4c\x00\x00\x0c\x00\x00\x00' + bytestring
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = b''
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x66\x00\x29\x01\x4f\x4c\x00\x00\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_UC_implicit_little(self):
        """Test writing elements with VR of UC works correctly."""
        # VM 1, even data
        elem = DataElement(0x00189908, 'UC', 'Test')
        encoded_elem = self.encode_element(elem)
        # Tag pair (0018, 9908): 08 00 20 01
        # Length (4): 04 00 00 00
        # Value: \x54\x65\x73\x74
        ref_bytes = b'\x18\x00\x08\x99\x04\x00\x00\x00\x54\x65\x73\x74'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 1, odd data - padded to even length
        elem.value = 'Test.'
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x18\x00\x08\x99\x06\x00\x00\x00\x54\x65\x73\x74\x2e\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 3, even data
        elem.value = ['Aa', 'B', 'C']
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x18\x00\x08\x99\x06\x00\x00\x00\x41\x61\x5c\x42\x5c\x43'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 3, odd data - padded to even length
        elem.value = ['A', 'B', 'C']
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x18\x00\x08\x99\x06\x00\x00\x00\x41\x5c\x42\x5c\x43\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = ''
        encoded_elem = self.encode_element(elem)
        ref_bytes = b'\x18\x00\x08\x99\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_UC_explicit_little(self):
        """Test writing elements with VR of UC works correctly.

        Elements with a VR of 'UC' use the newer explicit VR
        encoding (see PS3.5 Section 7.1.2).
        """
        # VM 1, even data
        elem = DataElement(0x00189908, 'UC', 'Test')
        encoded_elem = self.encode_element(elem, False, True)
        # Tag pair (0018, 9908): 08 00 20 01
        # VR (UC): \x55\x43
        # Reserved: \x00\x00
        # Length (4): \x04\x00\x00\x00
        # Value: \x54\x65\x73\x74
        ref_bytes = b'\x18\x00\x08\x99\x55\x43\x00\x00\x04\x00\x00\x00' \
                    b'\x54\x65\x73\x74'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 1, odd data - padded to even length
        elem.value = 'Test.'
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x18\x00\x08\x99\x55\x43\x00\x00\x06\x00\x00\x00' \
                    b'\x54\x65\x73\x74\x2e\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 3, even data
        elem.value = ['Aa', 'B', 'C']
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x18\x00\x08\x99\x55\x43\x00\x00\x06\x00\x00\x00' \
                    b'\x41\x61\x5c\x42\x5c\x43'
        self.assertEqual(encoded_elem, ref_bytes)

        # VM 3, odd data - padded to even length
        elem.value = ['A', 'B', 'C']
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x18\x00\x08\x99\x55\x43\x00\x00\x06\x00\x00\x00' \
                    b'\x41\x5c\x42\x5c\x43\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty data
        elem.value = ''
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x18\x00\x08\x99\x55\x43\x00\x00\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)

    def test_write_UR_implicit_little(self):
        """Test writing elements with VR of UR works correctly."""
        # Even length URL
        elem = DataElement(0x00080120, 'UR',
                           'http://github.com/darcymason/pydicom')
        encoded_elem = self.encode_element(elem)
        # Tag pair (0008, 2001): 08 00 20 01
        # Length (36): 24 00 00 00
        # Value: 68 to 6d
        ref_bytes = b'\x08\x00\x20\x01\x24\x00\x00\x00\x68\x74' \
                    b'\x74\x70\x3a\x2f\x2f\x67\x69\x74\x68\x75' \
                    b'\x62\x2e\x63\x6f\x6d\x2f\x64\x61\x72\x63' \
                    b'\x79\x6d\x61\x73\x6f\x6e\x2f\x70\x79\x64' \
                    b'\x69\x63\x6f\x6d'
        self.assertEqual(encoded_elem, ref_bytes)

        # Odd length URL has trailing \x20 (SPACE) padding
        elem.value = '../test/test.py'
        encoded_elem = self.encode_element(elem)
        # Tag pair (0008, 2001): 08 00 20 01
        # Length (16): 10 00 00 00
        # Value: 2e to 20
        ref_bytes = b'\x08\x00\x20\x01\x10\x00\x00\x00\x2e\x2e' \
                    b'\x2f\x74\x65\x73\x74\x2f\x74\x65\x73\x74' \
                    b'\x2e\x70\x79\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty value
        elem.value = ''
        encoded_elem = self.encode_element(elem)
        self.assertEqual(encoded_elem, b'\x08\x00\x20\x01\x00\x00\x00\x00')

    def test_write_UR_explicit_little(self):
        """Test writing elements with VR of UR works correctly.

        Elements with a VR of 'UR' use the newer explicit VR
        encoded (see PS3.5 Section 7.1.2).
        """
        # Even length URL
        elem = DataElement(0x00080120, 'UR', 'ftp://bits')
        encoded_elem = self.encode_element(elem, False, True)
        # Tag pair (0008, 2001): 08 00 20 01
        # VR (UR): \x55\x52
        # Reserved: \x00\x00
        # Length (4): \x0a\x00\x00\x00
        # Value: \x66\x74\x70\x3a\x2f\x2f\x62\x69\x74\x73
        ref_bytes = b'\x08\x00\x20\x01\x55\x52\x00\x00\x0a\x00\x00\x00' \
                    b'\x66\x74\x70\x3a\x2f\x2f\x62\x69\x74\x73'
        self.assertEqual(encoded_elem, ref_bytes)

        # Odd length URL has trailing \x20 (SPACE) padding
        elem.value = 'ftp://bit'
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x08\x00\x20\x01\x55\x52\x00\x00\x0a\x00\x00\x00' \
                    b'\x66\x74\x70\x3a\x2f\x2f\x62\x69\x74\x20'
        self.assertEqual(encoded_elem, ref_bytes)

        # Empty value
        elem.value = ''
        encoded_elem = self.encode_element(elem, False, True)
        ref_bytes = b'\x08\x00\x20\x01\x55\x52\x00\x00\x00\x00\x00\x00'
        self.assertEqual(encoded_elem, ref_bytes)


class TestCorrectAmbiguousVR(unittest.TestCase):
    """Test correct_ambiguous_vr."""
    def test_pixel_representation_vm_one(self):
        """Test correcting VM 1 elements which require PixelRepresentation."""
        ref_ds = Dataset()

        # If PixelRepresentation is 0 then VR should be US
        ref_ds.PixelRepresentation = 0
        ref_ds.SmallestValidPixelValue = b'\x00\x01' # Little endian 256
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.SmallestValidPixelValue, 256)
        self.assertEqual(ds[0x00280104].VR, 'US')

        # If PixelRepresentation is 1 then VR should be SS
        ref_ds.PixelRepresentation = 1
        ref_ds.SmallestValidPixelValue = b'\x00\x01' # Big endian 1
        ds = correct_ambiguous_vr(deepcopy(ref_ds), False)
        self.assertEqual(ds.SmallestValidPixelValue, 1)
        self.assertEqual(ds[0x00280104].VR, 'SS')

        # If no PixelRepresentation then should be unchanged
        ref_ds = Dataset()
        ref_ds.SmallestValidPixelValue = b'\x00\x01' # Big endian 1
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.SmallestValidPixelValue, b'\x00\x01')
        self.assertEqual(ds[0x00280104].VR, 'US or SS')

    def test_pixel_representation_vm_three(self):
        """Test correcting VM 3 elements which require PixelRepresentation."""
        ref_ds = Dataset()

        # If PixelRepresentation is 0 then VR should be US - Little endian
        ref_ds.PixelRepresentation = 0
        ref_ds.LUTDescriptor = b'\x01\x00\x00\x01\x10\x00' # 1\256\16
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.LUTDescriptor, [1, 256, 16])
        self.assertEqual(ds[0x00283002].VR, 'US')

        # If PixelRepresentation is 1 then VR should be SS
        ref_ds.PixelRepresentation = 1
        ref_ds.LUTDescriptor = b'\x01\x00\x00\x01\x00\x10'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), False)
        self.assertEqual(ds.LUTDescriptor, [256, 1, 16])
        self.assertEqual(ds[0x00283002].VR, 'SS')

        # If no PixelRepresentation then should be unchanged
        ref_ds = Dataset()
        ref_ds.LUTDescriptor = b'\x01\x00\x00\x01\x00\x10'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), False)
        self.assertEqual(ds.LUTDescriptor, b'\x01\x00\x00\x01\x00\x10')
        self.assertEqual(ds[0x00283002].VR, 'US or SS')

    def test_pixel_data(self):
        """Test correcting PixelData."""
        ref_ds = Dataset()

        # If BitsAllocated  > 8 then VR must be OW
        ref_ds.BitsAllocated = 16
        ref_ds.PixelData = b'\x00\x01' # Little endian 256
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True) # Little endian
        self.assertEqual(ds.PixelData, b'\x00\x01')
        self.assertEqual(ds[0x7fe00010].VR, 'OW')
        ds = correct_ambiguous_vr(deepcopy(ref_ds), False) # Big endian
        self.assertEqual(ds.PixelData, b'\x00\x01')
        self.assertEqual(ds[0x7fe00010].VR, 'OW')

        # If BitsAllocated <= 8 then VR can be OB or OW: OW
        ref_ds = Dataset()
        ref_ds.BitsAllocated = 8
        ref_ds.Rows = 2
        ref_ds.Columns = 2
        ref_ds.PixelData = b'\x01\x00\x02\x00\x03\x00\x04\x00'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.PixelData, b'\x01\x00\x02\x00\x03\x00\x04\x00')
        self.assertEqual(ds[0x7fe00010].VR, 'OW')

        # If BitsAllocated <= 8 then VR can be OB or OW: OB
        ref_ds = Dataset()
        ref_ds.BitsAllocated = 8
        ref_ds.Rows = 2
        ref_ds.Columns = 2
        ref_ds.PixelData = b'\x01\x02\x03\x04'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.PixelData, b'\x01\x02\x03\x04')
        self.assertEqual(ds[0x7fe00010].VR, 'OB')

        # If no BitsAllocated then VR should be unchanged
        ref_ds = Dataset()
        ref_ds.PixelData = b'\x00\x01' # Big endian 1
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.PixelData, b'\x00\x01')
        self.assertEqual(ds[0x7fe00010].VR, 'OB or OW')

        # If required elements missing then VR should be unchanged
        ref_ds = Dataset()
        ref_ds.BitsAllocated = 8
        ref_ds.Rows = 2
        ref_ds.PixelData = b'\x01\x02\x03\x04'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.PixelData, b'\x01\x02\x03\x04')
        self.assertEqual(ds[0x7fe00010].VR, 'OB or OW')

    def test_waveform_bits_allocated(self):
        """Test correcting elements which require WaveformBitsAllocated."""
        ref_ds = Dataset()

        # If WaveformBitsAllocated  > 8 then VR must be OW
        ref_ds.WaveformBitsAllocated = 16
        ref_ds.WaveformData = b'\x00\x01' # Little endian 256
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True) # Little endian
        self.assertEqual(ds.WaveformData, b'\x00\x01')
        self.assertEqual(ds[0x54001010].VR, 'OW')
        ds = correct_ambiguous_vr(deepcopy(ref_ds), False) # Big endian
        self.assertEqual(ds.WaveformData, b'\x00\x01')
        self.assertEqual(ds[0x54001010].VR, 'OW')

        # If WaveformBitsAllocated <= 8 then VR is OB or OW, but not sure which
        #   so leave VR unchanged
        ref_ds.WaveformBitsAllocated = 8
        ref_ds.WaveformData = b'\x01\x02'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.WaveformData, b'\x01\x02')
        self.assertEqual(ds[0x54001010].VR, 'OB or OW')

        # If no WaveformBitsAllocated then VR should be unchanged
        ref_ds = Dataset()
        ref_ds.WaveformData = b'\x00\x01' # Big endian 1
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.WaveformData, b'\x00\x01')
        self.assertEqual(ds[0x54001010].VR, 'OB or OW')

    def test_lut_descriptor(self):
        """Test correcting elements which require LUTDescriptor."""
        ref_ds = Dataset()
        ref_ds.PixelRepresentation = 0

        # If LUTDescriptor[0] is 1 then LUTData VR is 'US'
        ref_ds.LUTDescriptor = b'\x01\x00\x00\x01\x10\x00' # 1\256\16
        ref_ds.LUTData = b'\x00\x01' # Little endian 256
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True) # Little endian
        self.assertEqual(ds.LUTDescriptor[0], 1)
        self.assertEqual(ds[0x00283002].VR, 'US')
        self.assertEqual(ds.LUTData, 256)
        self.assertEqual(ds[0x00283006].VR, 'US')

        # If LUTDescriptor[0] is not 1 then LUTData VR is 'OW'
        ref_ds.LUTDescriptor = b'\x02\x00\x00\x01\x10\x00' # 2\256\16
        ref_ds.LUTData = b'\x00\x01\x00\x02'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True) # Little endian
        self.assertEqual(ds.LUTDescriptor[0], 2)
        self.assertEqual(ds[0x00283002].VR, 'US')
        self.assertEqual(ds.LUTData, b'\x00\x01\x00\x02')
        self.assertEqual(ds[0x00283006].VR, 'OW')

        # If no LUTDescriptor then VR should be unchanged
        ref_ds = Dataset()
        ref_ds.LUTData = b'\x00\x01'
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.LUTData, b'\x00\x01')
        self.assertEqual(ds[0x00283006].VR, 'US or OW')

    def test_overlay(self):
        """Test correcting OverlayData"""
        # Implicit VR must be 'OW'
        ref_ds = Dataset()
        ref_ds.is_implicit_VR = True
        ref_ds.add(DataElement(0x60003000, 'OB or OW', b'\x00'))
        ref_ds.add(DataElement(0x601E3000, 'OB or OW', b'\x00'))
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertTrue(ds[0x60003000].VR == 'OW')
        self.assertTrue(ds[0x601E3000].VR == 'OW')
        self.assertTrue(ref_ds[0x60003000].VR == 'OB or OW')
        self.assertTrue(ref_ds[0x601E3000].VR == 'OB or OW')

        # Explicit VR may be 'OB' or 'OW' (leave unchanged)
        ref_ds.is_implicit_VR = False
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertTrue(ds[0x60003000].VR == 'OB or OW')
        self.assertTrue(ref_ds[0x60003000].VR == 'OB or OW')

        # Missing is_implicit_VR (leave unchanged)
        del ref_ds.is_implicit_VR
        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertTrue(ds[0x60003000].VR == 'OB or OW')
        self.assertTrue(ref_ds[0x60003000].VR == 'OB or OW')

    def test_sequence(self):
        """Test correcting elements in a sequence."""
        ref_ds = Dataset()
        ref_ds.BeamSequence = [Dataset()]
        ref_ds.BeamSequence[0].PixelRepresentation = 0
        ref_ds.BeamSequence[0].SmallestValidPixelValue = b'\x00\x01'
        ref_ds.BeamSequence[0].BeamSequence = [Dataset()]
        ref_ds.BeamSequence[0].BeamSequence[0].PixelRepresentation = 0
        ref_ds.BeamSequence[0].BeamSequence[0].SmallestValidPixelValue = b'\x00\x01'

        ds = correct_ambiguous_vr(deepcopy(ref_ds), True)
        self.assertEqual(ds.BeamSequence[0].SmallestValidPixelValue, 256)
        self.assertEqual(ds.BeamSequence[0][0x00280104].VR, 'US')
        self.assertEqual(ds.BeamSequence[0].BeamSequence[0].SmallestValidPixelValue, 256)
        self.assertEqual(ds.BeamSequence[0].BeamSequence[0][0x00280104].VR, 'US')


class WriteAmbiguousVRTests(unittest.TestCase):
    """Attempt to write data elements with ambiguous VR."""
    def setUp(self):
        # Create a dummy (in memory) file to write to
        self.fp = DicomBytesIO()
        self.fp.is_implicit_VR = False
        self.fp.is_little_endian = True

    def test_write_explicit_vr_raises(self):
        """Test writing explicit vr raises exception if unsolved element."""
        ds = Dataset()
        ds.PerimeterValue = b'\x00\x01'

        def test():
            write_dataset(self.fp, ds)

        self.assertRaises(ValueError, test)

    def test_write_explicit_vr_little_endian(self):
        """Test writing explicit little data for ambiguous elements."""
        # Create a dataset containing element with ambiguous VRs
        ref_ds = Dataset()
        ref_ds.PixelRepresentation = 0
        ref_ds.SmallestValidPixelValue = b'\x00\x01' # Little endian 256

        fp = BytesIO()
        file_ds = FileDataset(fp, ref_ds)
        file_ds.is_implicit_VR = False
        file_ds.is_little_endian = True
        file_ds.save_as(fp)
        fp.seek(0)

        ds = read_dataset(fp, False, True)
        self.assertEqual(ds.SmallestValidPixelValue, 256)
        self.assertEqual(ds[0x00280104].VR, 'US')

    def test_write_explicit_vr_big_endian(self):
        """Test writing explicit big data for ambiguous elements."""
        # Create a dataset containing element with ambiguous VRs
        ref_ds = Dataset()
        ref_ds.PixelRepresentation = 1
        ref_ds.SmallestValidPixelValue = b'\x00\x01' # Big endian 1

        fp = BytesIO()
        file_ds = FileDataset(fp, ref_ds)
        file_ds.is_implicit_VR = False
        file_ds.is_little_endian = False
        file_ds.save_as(fp)
        fp.seek(0)

        ds = read_dataset(fp, False, False)
        self.assertEqual(ds.SmallestValidPixelValue, 1)
        self.assertEqual(ds[0x00280104].VR, 'SS')


class ScratchWriteTests(unittest.TestCase):
    """Simple dataset from scratch, written in all endian/VR combinations"""
    def setUp(self):
        # Create simple dataset for all tests
        ds = Dataset()
        ds.PatientName = "Name^Patient"
        ds.InstanceNumber = None

        # Set up a simple nested sequence
        # first, the innermost sequence
        subitem1 = Dataset()
        subitem1.ContourNumber = 1
        subitem1.ContourData = ['2', '4', '8', '16']
        subitem2 = Dataset()
        subitem2.ContourNumber = 2
        subitem2.ContourData = ['32', '64', '128', '196']

        sub_ds = Dataset()
        sub_ds.ContourSequence = Sequence((subitem1, subitem2))

        # Now the top-level sequence
        ds.ROIContourSequence = Sequence((sub_ds,))  # Comma to make one-tuple

        # Store so each test can use it
        self.ds = ds

    def compare_write(self, hex_std, file_ds):
        """Write file and compare with expected byte string

        :arg hex_std: the bytes which should be written, as space separated hex
        :arg file_ds: a FileDataset instance containing the dataset to write
        """
        out_filename = "scratch.dcm"
        file_ds.save_as(out_filename)
        std = hex2bytes(hex_std)
        with open(out_filename, 'rb') as f:
            bytes_written = f.read()
        # print "std    :", bytes2hex(std)
        # print "written:", bytes2hex(bytes_written)
        same, pos = bytes_identical(std, bytes_written)
        self.assertTrue(same,
                        "Writing from scratch unexpected result - 1st diff at 0x%x" % pos)
        if os.path.exists(out_filename):
            os.remove(out_filename)  # get rid of the file

    def testImpl_LE_deflen_write(self):
        """Scratch Write for implicit VR little endian, defined length SQ's"""
        from _write_stds import impl_LE_deflen_std_hex as std

        file_ds = FileDataset("test", self.ds)
        self.compare_write(std, file_ds)


class TestWriteToStandard(unittest.TestCase):
    """Unit tests for writing datasets to the DICOM standard"""
    def setUp(self):
        """Create an empty file-like for use in testing."""
        self.fp = BytesIO()

    def test_preamble_default(self):
        """Test that the default preamble is written correctly when present."""
        ds = read_file(ct_name)
        ds.preamble = b'\x00' * 128
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x00' * 128)

    def test_preamble_custom(self):
        """Test that a custom preamble is written correctly when present."""
        ds = read_file(ct_name)
        ds.preamble = b'\x01\x02\x03\x04' + b'\x00' * 124
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x01\x02\x03\x04' + b'\x00' * 124)

    def test_no_preamble(self):
        """Test that a default preamble is written when absent."""
        ds = read_file(ct_name)
        del ds.preamble
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x00' * 128)

    def test_none_preamble(self):
        """Test that a default preamble is written when None."""
        ds = read_file(ct_name)
        ds.preamble = None
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x00' * 128)

    def test_bad_preamble(self):
        """Test that ValueError is raised when preamble is bad."""
        ds = read_file(ct_name)
        ds.preamble = b'\x00' * 127
        self.assertRaises(ValueError, ds.save_as, self.fp, write_like_original=False)
        ds.preamble = b'\x00' * 129
        self.assertRaises(ValueError, ds.save_as, self.fp, write_like_original=False)

    def test_prefix(self):
        """Test that the 'DICM' prefix is written with preamble."""
        # Has preamble
        ds = read_file(ct_name)
        ds.preamble = b'\x00' * 128
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(128)
        self.assertEqual(self.fp.read(4), b'DICM')

    def test_prefix_none(self):
        """Test the 'DICM' prefix is written when preamble is None"""
        ds = read_file(ct_name)
        ds.preamble = None
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(128)
        self.assertEqual(self.fp.read(4), b'DICM')

    def test_ds_unchanged(self):
        """Test writing the dataset doesn't change it."""
        ds = read_file(rtplan_name)
        ref_ds = read_file(rtplan_name)
        # Ensure no RawDataElements in ref_ds
        for elem in ref_ds.file_meta: pass
        for elem in ref_ds.iterall(): pass
        ds.save_as(self.fp, write_like_original=False)
        self.assertTrue(ref_ds.file_meta == ds.file_meta)
        self.assertTrue(ref_ds == ds)

    def test_transfer_syntax_added(self):
        """Test TransferSyntaxUID is added/updated if possible."""
        # Only done for ImplVR LE and ExplVR BE
        # Added
        ds = read_file(rtplan_name)
        ds.is_implicit_VR = True
        ds.is_little_endian = True
        ds.save_as(self.fp, write_like_original=False)
        self.assertEqual(ds.file_meta.TransferSyntaxUID, ImplicitVRLittleEndian)

        # Updated
        ds.is_implicit_VR = False
        ds.is_little_endian = False
        ds.save_as(self.fp, write_like_original=False)
        self.assertEqual(ds.file_meta.TransferSyntaxUID, ExplicitVRBigEndian)

    def test_transfer_syntax_not_added(self):
        """Test TransferSyntaxUID is not added if ExplVRLE."""
        ds = read_file(rtplan_name)
        del ds.file_meta.TransferSyntaxUID
        ds.is_implicit_VR = False
        ds.is_little_endian = True
        self.assertRaises(ValueError, ds.save_as, self.fp, write_like_original=False)
        self.assertFalse('TransferSyntaxUID' in ds.file_meta)

    def test_transfer_syntax_raises(self):
        """Test TransferSyntaxUID is raises NotImplementedError if ImplVRBE."""
        ds = read_file(rtplan_name)
        ds.is_implicit_VR = True
        ds.is_little_endian = False
        self.assertRaises(NotImplementedError, ds.save_as, self.fp, write_like_original=False)

    def test_raise_no_file_meta(self):
        """Test exception is raised if trying to write a dataset with no file_meta"""
        ds = read_file(rtplan_name)
        ds.file_meta = Dataset()
        self.assertRaises(ValueError, ds.save_as, self.fp, write_like_original=False)
        del ds.file_meta
        self.assertRaises(ValueError, ds.save_as, self.fp, write_like_original=False)

    def test_standard(self):
        """Test preamble + file_meta + dataset written OK."""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp)
        self.assertEqual(ds_out.preamble, preamble)
        self.assertTrue('PatientID' in ds_out)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)

    def test_commandset_no_written(self):
        """Test that Command Set elements are not written when writing to standard"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        ds.MessageID = 3
        ds.save_as(self.fp, write_like_original=False)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')
        self.assertTrue('MessageID' in ds)

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp)
        self.assertEqual(ds_out.preamble, preamble)
        self.assertTrue('PatientID' in ds_out)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)
        self.assertFalse('MessageID' in ds_out)


class TestWriteFileMetaInfoToStandard(unittest.TestCase):
    """Unit tests for writing File Meta Info to the DICOM standard."""
    def setUp(self):
        """Create an empty file-like for use in testing."""
        self.fp = DicomBytesIO()

    def test_bad_elements(self):
        """Test that non-group 2 elements aren't written to the file meta."""
        meta = Dataset()
        meta.PatientID = '12345678'
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta,
                          enforce_standard=True)

    def test_missing_elements(self):
        """Test that missing required elements raises ValueError."""
        meta = Dataset()
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta)
        meta.MediaStorageSOPClassUID = '1.1'
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta)
        meta.MediaStorageSOPInstanceUID = '1.2'
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta)
        meta.TransferSyntaxUID = '1.3'
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta)
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=True)

    def test_group_length(self):
        """Test that the value for FileMetaInformationGroupLength is OK."""
        meta = Dataset()
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=True)

        # 74 in total, - 12 for group length = 62
        self.fp.seek(8)
        self.assertEqual(self.fp.read(4), b'\x3E\x00\x00\x00')

    def test_group_length_updated(self):
        """Test that FileMetaInformationGroupLength gets updated if present."""
        meta = Dataset()
        meta.FileMetaInformationGroupLength = 100 # Not actual length
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=True)

        self.fp.seek(8)
        self.assertEqual(self.fp.read(4), b'\x3E\x00\x00\x00')
        # Check original file meta is unchanged/updated
        self.assertEqual(meta.FileMetaInformationGroupLength, 62)
        self.assertEqual(meta.FileMetaInformationVersion, b'\x00\x01')
        self.assertEqual(meta.MediaStorageSOPClassUID, '1.1')
        self.assertEqual(meta.MediaStorageSOPInstanceUID, '1.2')
        self.assertEqual(meta.TransferSyntaxUID, '1.3')
        self.assertEqual(meta.ImplementationClassUID, '1.4')

    def test_version(self):
        """Test that the value for FileMetaInformationVersion is OK."""
        meta = Dataset()
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=True)

        self.fp.seek(12 + 12)
        self.assertEqual(self.fp.read(2), b'\x00\x01')

    def test_filelike_position(self):
        """Test that the file-like's ending position is OK."""
        # 8 + 4 bytes FileMetaInformationGroupLength
        # 12 + 2 bytes FileMetaInformationVersion
        # 8 + 4 bytes MediaStorageSOPClassUID
        # 8 + 4 bytes MediaStorageSOPInstanceUID
        # 8 + 4 bytes TransferSyntaxUID
        # 8 + 4 bytes ImplementationClassUID
        # 74 bytes total
        meta = Dataset()
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=True)
        self.assertEqual(self.fp.tell(), 74)

        # 8 + 6 bytes ImplementationClassUID
        # 76 bytes total, group length 64
        self.fp.seek(0)
        meta.ImplementationClassUID = '1.4.1'
        write_file_meta_info(self.fp, meta, enforce_standard=True)
        # Check File Meta length
        self.assertEqual(self.fp.tell(), 76)
        # Check Group Length
        self.fp.seek(8)
        self.assertEqual(self.fp.read(4), b'\x40\x00\x00\x00')


class TestWriteNonStandard(unittest.TestCase):
    """Unit tests for writing datasets not to the DICOM standard."""
    def setUp(self):
        """Create an empty file-like for use in testing."""
        self.fp = DicomBytesIO()
        self.fp.is_little_endian = True
        self.fp.is_implicit_VR = True

    def compare_bytes(self, bytes_in, bytes_out):
        """Compare two bytestreams for equality"""
        same, pos = bytes_identical(bytes_in, bytes_out)
        self.assertTrue(same, "Bytestreams are not identical - first "
                        "difference at 0x%x" %pos)

    def test_preamble_default(self):
        """Test that the default preamble is written correctly when present."""
        ds = read_file(ct_name)
        ds.preamble = b'\x00' * 128
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x00' * 128)

    def test_preamble_custom(self):
        """Test that a custom preamble is written correctly when present."""
        ds = read_file(ct_name)
        ds.preamble = b'\x01\x02\x03\x04' + b'\x00' * 124
        self.fp.seek(0)
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), b'\x01\x02\x03\x04' + b'\x00' * 124)

    def test_no_preamble(self):
        """Test no preamble or prefix is written if preamble absent."""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds.preamble
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), b'\x00' * 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), preamble)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')

    def test_ds_unchanged(self):
        """Test writing the dataset doesn't change it."""
        ds = read_file(rtplan_name)
        ref_ds = read_file(rtplan_name)
        # Ensure no RawDataElements in ref_ds
        for elem in ref_ds.file_meta: pass
        for elem in ref_ds.iterall(): pass
        ds.save_as(self.fp, write_like_original=True)
        self.assertTrue(ref_ds == ds)

    def test_file_meta_unchanged(self):
        """Test no file_meta elements are added if missing."""
        ds = read_file(rtplan_name)
        ds.file_meta = Dataset()
        ds.save_as(self.fp, write_like_original=True)
        self.assertEqual(ds.file_meta, Dataset())

    def test_dataset(self):
        """Test dataset written OK with no preamble or file meta"""
        ds = read_file(ct_name)
        del ds.preamble
        del ds.file_meta
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), b'\x00' * 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.preamble, None)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('PatientID' in ds_out)

    def test_preamble_dataset(self):
        """Test dataset written OK with no file meta"""
        ds = read_file(ct_name)
        del ds.file_meta
        preamble = ds.preamble[:]
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('PatientID' in ds_out)

    def test_filemeta_dataset(self):
        """Test file meta written OK if preamble absent."""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds.preamble
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), b'\x00' * 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), preamble)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertTrue('ImplementationClassUID' in ds_out.file_meta)
        self.assertEqual(ds_out.preamble, None)
        self.assertTrue('PatientID' in ds_out)

    def test_preamble_filemeta_dataset(self):
        """Test non-standard file meta written with preamble OK"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds.file_meta[:], ds_out.file_meta[:])
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta[:])
        self.assertEqual(ds_out.preamble, preamble)
        self.assertTrue('PatientID' in ds_out)

    def test_commandset_dataset(self):
        """Test written OK with command set/dataset"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds.preamble
        del ds.file_meta
        ds.is_little_endian = True
        ds.is_implicit_VR = True
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), preamble)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), b'\x00' * 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VRe
        self.fp.seek(0)
        self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('Status' in ds_out)
        self.assertTrue('PatientID' in ds_out)

    def test_preamble_commandset_dataset(self):
        """Test written OK with preamble/command set/dataset"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds.file_meta
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('Status' in ds_out)
        self.assertTrue('PatientID' in ds_out)

    def test_preamble_commandset_filemeta_dataset(self):
        """Test written OK with preamble/command set/file meta/dataset"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), preamble)
        self.assertEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        #self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)
        self.assertTrue('Status' in ds_out)
        self.assertTrue('PatientID' in ds_out)

    def test_commandset_filemeta_dataset(self):
        """Test written OK with command set/file meta/dataset"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds.preamble
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), preamble)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), b'\x00' * 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        self.fp.seek(0)
        #self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)
        self.assertTrue('Status' in ds_out)
        self.assertTrue('PatientID' in ds_out)

    def test_commandset(self):
        """Test written OK with command set"""
        ds = read_file(ct_name)
        del ds[:]
        del ds.preamble
        del ds.file_meta
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertRaises(EOFError, self.fp.read, 128)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        self.fp.seek(0)
        #self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('Status' in ds_out)
        self.assertFalse('PatientID' in ds_out)
        self.assertEqual(ds_out[0x00010000:], Dataset())

    def test_commandset_filemeta(self):
        """Test dataset written OK with command set/file meta"""
        ds = read_file(ct_name)
        preamble = ds.preamble[:]
        del ds[:]
        del ds.preamble
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(128), preamble)
        self.fp.seek(0)
        self.assertNotEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        self.fp.seek(0)
        #self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)
        self.assertTrue('Status' in ds_out)
        self.assertFalse('PatientID' in ds_out)
        self.assertEqual(ds_out[0x00010000:], Dataset())

    def test_preamble_commandset(self):
        """Test written OK with preamble/command set"""
        ds = read_file(ct_name)
        del ds[:]
        del ds.file_meta
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), ds.preamble)
        self.assertEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertEqual(ds_out.file_meta, Dataset())
        self.assertTrue('Status' in ds_out)
        self.assertFalse('PatientID' in ds_out)
        self.assertEqual(ds_out[0x00010000:], Dataset())

    def test_preamble_commandset_filemeta(self):
        """Test written OK with preamble/command set/file meta"""
        ds = read_file(ct_name)
        del ds[:]
        ds.CommandGroupLength = 8
        ds.MessageID = 1
        ds.MoveDestination = 'SOME_SCP'
        ds.Status = 0x0000
        ds.save_as(self.fp, write_like_original=True)
        self.fp.seek(0)
        self.assertEqual(self.fp.read(128), ds.preamble)
        self.assertEqual(self.fp.read(4), b'DICM')
        # Ensure Command Set Elements written as little endian implicit VR
        #self.assertEqual(self.fp.read(12), b'\x00\x00\x00\x00\x04\x00\x00\x00\x08\x00\x00\x00')

        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        ds_out = read_file(fp, force=True)
        self.assertTrue('Status' in ds_out)
        self.assertTrue('TransferSyntaxUID' in ds_out.file_meta)
        self.assertFalse('PatientID' in ds_out)
        self.assertEqual(ds_out[0x00010000:], Dataset())

    def test_read_write_identical(self):
        """Test the written bytes matches the read bytes."""
        for dcm_in in [rtplan_name, rtdose_name, ct_name, mr_name, jpeg_name,
                        no_ts, unicode_name, multiPN_name]:
            with open(dcm_in, 'rb') as f:
                bytes_in = BytesIO(f.read())
                ds_in = read_file(bytes_in)
                bytes_out = BytesIO()
                ds_in.save_as(bytes_out, write_like_original=True)
                self.compare_bytes(bytes_in.getvalue(), bytes_out.getvalue())


class TestWriteFileMetaInfoNonStandard(unittest.TestCase):
    """Unit tests for writing File Meta Info not to the DICOM standard."""
    def setUp(self):
        """Create an empty file-like for use in testing."""
        self.fp = DicomBytesIO()

    def test_transfer_syntax_not_added(self):
        """Test that the TransferSyntaxUID isn't added if missing"""
        ds = read_file(no_ts)
        write_file_meta_info(self.fp, ds.file_meta, enforce_standard=False)
        self.assertFalse('TransferSyntaxUID' in ds.file_meta)
        self.assertTrue('ImplementationClassUID' in ds.file_meta)

        # Check written meta dataset doesn't contain TransferSyntaxUID
        fp = BytesIO(self.fp.getvalue()) # Workaround to avoid #358
        written_ds = read_file(fp, force=True)
        self.assertTrue('ImplementationClassUID' in written_ds.file_meta)
        self.assertFalse('TransferSyntaxUID' in written_ds.file_meta)

    def test_bad_elements(self):
        """Test that non-group 2 elements aren't written to the file meta."""
        meta = Dataset()
        meta.PatientID = '12345678'
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        self.assertRaises(ValueError, write_file_meta_info, self.fp, meta,
                          enforce_standard=False)

    def test_missing_elements(self):
        """Test that missing required elements doesn't raise ValueError."""
        meta = Dataset()
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        meta.MediaStorageSOPClassUID = '1.1'
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        meta.MediaStorageSOPInstanceUID = '1.2'
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        meta.TransferSyntaxUID = '1.3'
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=False)

    def test_group_length_updated(self):
        """Test that FileMetaInformationGroupLength gets updated if present."""
        meta = Dataset()
        meta.FileMetaInformationGroupLength = 100
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=False)

        # 8 + 4 bytes FileMetaInformationGroupLength
        # 8 + 4 bytes MediaStorageSOPClassUID
        # 8 + 4 bytes MediaStorageSOPInstanceUID
        # 8 + 4 bytes TransferSyntaxUID
        # 8 + 4 bytes ImplementationClassUID
        # 60 bytes total, - 12 for group length = 48
        self.fp.seek(8)
        self.assertEqual(self.fp.read(4), b'\x30\x00\x00\x00')
        # Check original file meta is unchanged/updated
        self.assertEqual(meta.FileMetaInformationGroupLength, 48)
        self.assertFalse('FileMetaInformationVersion' in meta)
        self.assertEqual(meta.MediaStorageSOPClassUID, '1.1')
        self.assertEqual(meta.MediaStorageSOPInstanceUID, '1.2')
        self.assertEqual(meta.TransferSyntaxUID, '1.3')
        self.assertEqual(meta.ImplementationClassUID, '1.4')

    def test_filelike_position(self):
        """Test that the file-like's ending position is OK."""
        # 8 + 4 bytes MediaStorageSOPClassUID
        # 8 + 4 bytes MediaStorageSOPInstanceUID
        # 8 + 4 bytes TransferSyntaxUID
        # 8 + 4 bytes ImplementationClassUID
        # 48 bytes total
        meta = Dataset()
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        self.assertEqual(self.fp.tell(), 48)

        # 8 + 6 bytes ImplementationClassUID
        # 50 bytes total
        self.fp.seek(0)
        meta.ImplementationClassUID = '1.4.1'
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        # Check File Meta length
        self.assertEqual(self.fp.tell(), 50)

    def test_meta_unchanged(self):
        """Test that the meta dataset doesn't change when writing it"""
        # Empty
        meta = Dataset()
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        self.assertEqual(meta, Dataset())

        # Incomplete
        meta = Dataset()
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        ref_meta = deepcopy(meta)
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        self.assertEqual(meta, ref_meta)

        # Conformant
        meta = Dataset()
        meta.FileMetaInformationGroupLength = 62 # Correct length
        meta.FileMetaInformationVersion = b'\x00\x01'
        meta.MediaStorageSOPClassUID = '1.1'
        meta.MediaStorageSOPInstanceUID = '1.2'
        meta.TransferSyntaxUID = '1.3'
        meta.ImplementationClassUID = '1.4'
        ref_meta = deepcopy(meta)
        write_file_meta_info(self.fp, meta, enforce_standard=False)
        self.assertEqual(meta, ref_meta)


if __name__ == "__main__":
    # This is called if run alone, but not if loaded through run_tests.py
    # If not run from the directory where the sample images are,
    #    then need to switch there
    unittest.main()
