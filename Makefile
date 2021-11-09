all:	clean build cleanbuild

clean:
	-/usr/bin/rm -rf dist BUILD BUILDROOT RPMS SRPMS MANIFEST *.egg-info

build:
	python3 setup.py sdist
	rpmbuild -ba -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" python-cpio.spec
	#mock -r epel-8-x86_64 --rebuild SRPMS/*.src.rpm
	#mock -r epel-7-x86_64 --rebuild SRPMS/*.src.rpm

cleanbuild:
	-/usr/bin/rm -rf dist BUILD BUILDROOT MANIFEST