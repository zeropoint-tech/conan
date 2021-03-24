pipeline {

  agent any

  stages {
	  stage('Conan configuration') {
      steps {
        rtConanClient (id: "myConanClient")
        rtConanRemote (
          name: "artifactory",
          serverId: "artifactory",
          repo: "conan-local",
          clientId: "myConanClient",
        )
      }
    }

    stage('Export recipies') {
      steps {
        rtConanRun(
          clientId: "myConanClient",
          command: "export semver"
        )
      }
    }
  }

}
